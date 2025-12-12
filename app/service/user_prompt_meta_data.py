from app.data.user_prompt_meta_data import get_prompt_metadata
from app.model.user_prompt_meta_data import PromptMetaData
from app.model.user_prompt_response import UserPromptResponse,  PlanDetailForUserManagement, ActivityByDayIdentifier, WeeklyPlanIdentifier, WeeklyPlan, ActivityDetail, ActivityDetailIdentifier, UXUserPromptInfo, UXGoalBuilder
from app.model.common import RoutineSummary, GeneralRecommendationAndGuidelines
from app.data.user_plan_detail import insert_activity_detail, insert_daily_header, insert_weekly_header
from app.data.user_plan import get_goal_builder, insert_goal_builder, insert_general_guideline, insert_plan_routine_summary, insert_created_plan
from app.model.user_plan import UXUserPlanIdentifier, ICreatedPlan
from app.data.dbinit import get_db
from app.data.user import User
from fastapi import APIRouter, Depends, HTTPException, status, Query
from openai import OpenAI, OpenAIError
from app.config.config import settings
from typing import Dict, Optional, Tuple
from app.model.user_plan import UserPlanIdentifier, UserPlan
from app.data import user_plan
import structlog
import requests
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.common.utility_functions import count_words_alpha_numeric
from app.common.exception import IntegrityException, GeneralDataException, UserNotFound, YoudraGeminiError, YoudraOpenAIError, PlanContextChange, PlanIllegalText, NotEnoughInfoToGenerateGoal
from app.common.qdrant_common import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams, Filter, FieldCondition, MatchValue
from app.common.messaging import publish_message
import aio_pika
import uuid
import re
from enum import Enum
from app.common.site_enums import Level, EntityType, PlanStatus
from app.service.context_manager import detect_context_switch, detect_context_switch_gemini
import random 
from pydantic import ValidationError
import google.generativeai as genai
import json
from app.model.user_prompt_response import MileStone, WeeklyPlanWithDailyDetail, ActivityByDayDetail
#from openai.types.beta.chat_completions import ChatCompletionParsedResponse
#from openai.types import ChatCompletion

# Set up logging
logger = structlog.get_logger()

async def parse_activity(input_str: str) -> Tuple[str, str, str]:
    if not input_str or not input_str.strip():
        return "", "", ""
    
    input_str = input_str.strip()

    if "—" in input_str:  # em dash
        parts = input_str.split("—")
        activity_desc = parts[0].strip()
        suggested_duration = ""
        suggested_repetition = ""

        for part in parts[1:]:
            part = part.strip().lower()
            if "suggested duration" in part:
                match = re.search(r"(\d+)", part)
                if match:
                    suggested_duration = match.group(1)
            elif "suggested repetition" in part:
                match = re.search(r"(\d+)", part)
                if match:
                    suggested_repetition = match.group(1)

        return activity_desc, suggested_duration, suggested_repetition
    else:
        return input_str, "", ""


async def load_plan(obj_user_profile: UserPromptResponse, 
                    db: AsyncSession, 
                    current_user: User,
                    msg_connection: aio_pika.RobustConnection,
                    ic_root_id = None,
                    ic_prev_plan_id = None):
    try:

        obj_created_plan = []
        message = {}
        message_detail = {}
        logger.info(f"Inserting the user plan for user {current_user.user_id}")

        obj_user_plan = UserPlan(user_id= current_user.user_id,
                                 plan_name = obj_user_profile.plan_name,
                                 plan_type = obj_user_profile.plan_type,
                                 plan_goal = obj_user_profile.Goal,
                                 goal_duration=obj_user_profile.GoalDuration,
                                 plan_category=obj_user_profile.plan_category,
                                 plan_status=0)

    # Perform database operations

        obj_user_plan_db = await user_plan.insert_plan( obj_user_plan, db)
        message["plan_id"] = str(obj_user_plan_db.plan_id)
        message["user_id"] = str(obj_user_plan_db.user_id)
        if ic_root_id is None:
            ic_prev_plan_id = ic_root_id = str(obj_user_plan_db.plan_id)
        
        obj_user_plan_ux = UXUserPlanIdentifier(user_id = str(obj_user_plan_db.user_id),
                                              plan_id = str(obj_user_plan_db.plan_id),
                                              plan_name = obj_user_plan_db.plan_name,
                                              plan_type = obj_user_plan_db.plan_type,
                                              plan_goal = obj_user_plan_db.plan_goal,
                                              plan_end_date= obj_user_plan_db.plan_end_date,
                                              plan_start_date= obj_user_plan_db.plan_start_date,
                                              root_id=ic_root_id,
                                              prev_plan_id=ic_prev_plan_id
                                              )
        if not obj_user_plan_db:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user plan"
            )      
        logger.info(f"User plan is successfully inserted and the plan id is {obj_user_plan_db.plan_id}")
        if obj_user_profile.plan_type == "Weekly":
            print ("The number of week count is ", len(obj_user_profile.plan))
            for i in range(len(obj_user_profile.plan)):
                week_sequence_id = (i+1)*10000
                obj_wk_created_plan = ICreatedPlan(plan_id=obj_user_plan_db.plan_id,
                                                sequence_id= week_sequence_id,
                                                level_id=Level.ROOT,
                                                entity_type=EntityType.WEEK,
                                                parent_id=None,
                                                suggested_start_time=None,
                                                suggestion_duration=None,
                                                status_id=1,
                                                source_id=0,
                                                entity_desc=obj_user_profile.plan[i].weekly_objective)
                obj_wk_created_plan_db = await insert_created_plan(obj_wk_created_plan,db)
                obj_created_plan.append(obj_wk_created_plan_db)
                message_detail[str(obj_wk_created_plan_db.entity_id)] = obj_wk_created_plan_db.entity_desc

                for j in range(len(obj_user_profile.plan[i].dailyactivity)):
                    day_sequence_id = week_sequence_id + (j+1)*100
                    obj_d_created_plan = ICreatedPlan(plan_id=obj_user_plan_db.plan_id,
                                sequence_id= day_sequence_id,
                                level_id=Level.BRANCH,
                                entity_type=EntityType.DAY,
                                parent_id=obj_wk_created_plan_db.entity_id,
                                suggested_start_time=obj_user_profile.plan[i].dailyactivity[j].suggested_time,
                                suggestion_duration=obj_user_profile.plan[i].dailyactivity[j].suggested_duration,
                                status_id=1,
                                source_id=0,
                                entity_desc=obj_user_profile.plan[i].dailyactivity[j].daily_objective)
                    
                    obj_d_created_plan_db = await insert_created_plan(obj_d_created_plan,db)
                    message_detail[str(obj_d_created_plan_db.entity_id)] = obj_d_created_plan_db.entity_desc
                    obj_created_plan.append(obj_d_created_plan_db)

                    for k in range(len( obj_user_profile.plan[i].dailyactivity[j].activity_detail)):

                        activity_sequence_id = day_sequence_id + (k+1)
                        activity_description, activity_time, activity_duration = await parse_activity(obj_user_profile.plan[i].dailyactivity[j].activity_detail[k].activity)
                        obj_activity_created_plan = ICreatedPlan(plan_id=obj_user_plan_db.plan_id,
                                sequence_id= activity_sequence_id,
                                level_id=Level.LEAF,
                                entity_type=EntityType.ACTIVITY,
                                parent_id=obj_d_created_plan_db.entity_id,
                                suggested_start_time= activity_time, #obj_user_profile.plan[i].dailyactivity[j].suggested_time,
                                suggestion_duration=activity_duration , # obj_user_profile.plan[i].dailyactivity[j].suggested_duration,
                                status_id=1,
                                source_id=0,
                                entity_desc= activity_description) #obj_user_profile.plan[i].dailyactivity[j].activity_detail[k].activity)
                    
                        obj_activity_created_plan_db = await insert_created_plan(obj_activity_created_plan,db)
                        message_detail[str(obj_activity_created_plan_db.entity_id)] = obj_activity_created_plan_db.entity_desc
                        obj_created_plan.append(obj_activity_created_plan_db)


        elif obj_user_profile.plan_type == "Daily":
            for i in range(len(obj_user_profile.plan)):
                day_sequence_id = (i+1)*10000
                obj_d_created_plan = ICreatedPlan(plan_id=obj_user_plan_db.plan_id,
                                sequence_id= day_sequence_id,
                                level_id=Level.ROOT,
                                entity_type=EntityType.DAY,
                                parent_id=None,
                                suggested_start_time=obj_user_profile.plan[i].suggested_time,
                                suggestion_duration=obj_user_profile.plan[i].suggested_duration,
                                status_id=1,
                                source_id=0,
                                entity_desc=obj_user_profile.plan[i].daily_objective)
                    
                obj_d_created_plan_db = await insert_created_plan(obj_d_created_plan,db)
                message_detail[str(obj_d_created_plan_db.entity_id)] = obj_d_created_plan_db.entity_desc
                obj_created_plan.append(obj_d_created_plan_db)


                for k in range(len( obj_user_profile.plan[i].activity_detail)):
                    (activity_description, activity_time, activity_duration) = await parse_activity(obj_user_profile.plan[i].activity_detail[k].activity)
                    activity_sequence_id = day_sequence_id + (k+1)
                    obj_activity_created_plan = ICreatedPlan(plan_id=obj_user_plan_db.plan_id,
                            sequence_id= activity_sequence_id,
                            level_id=Level.LEAF,
                            entity_type=EntityType.ACTIVITY,
                            parent_id=obj_d_created_plan_db.entity_id,
                            suggested_start_time= activity_time, #obj_user_profile.plan[i].suggested_time,
                            suggestion_duration=activity_duration, #obj_user_profile.plan[i].suggested_duration,
                            status_id=1,
                            source_id=0,
                            entity_desc=activity_description) #obj_user_profile.plan[i].activity_detail[k].activity)
                
                    obj_activity_created_plan_db = await insert_created_plan(obj_activity_created_plan,db)
                    message_detail[str(obj_activity_created_plan_db.entity_id)] = obj_activity_created_plan_db.entity_desc
                    obj_created_plan.append(obj_activity_created_plan_db)

        else:
            print ("This is a plan request with no time criteria")
            magic_day_number_constant = "Day-0"
            for i in range(len(obj_user_profile.plan)):
                week_sequence_id = (i+1)*10000
                obj_ms_created_plan = ICreatedPlan(plan_id=obj_user_plan_db.plan_id,
                                                sequence_id= week_sequence_id,
                                                level_id=Level.ROOT,
                                                entity_type=EntityType.MILESTONE,
                                                parent_id=None,
                                                suggested_start_time=None,
                                                suggestion_duration=None,
                                                status_id=1,
                                                source_id=0,
                                                entity_desc=obj_user_profile.plan[i].milestone_desc)
                obj_ms_created_plan_db = await insert_created_plan(obj_ms_created_plan,db)
                obj_created_plan.append(obj_ms_created_plan_db)
                message_detail[str(obj_ms_created_plan_db.entity_id)] = obj_ms_created_plan_db.entity_desc

                for j in range(len(obj_user_profile.plan[i].activities)):
                    day_sequence_id = week_sequence_id + (j+1)*100
                    obj_d_created_plan = ICreatedPlan(plan_id=obj_user_plan_db.plan_id,
                                    sequence_id= day_sequence_id,
                                    level_id=Level.BRANCH,
                                    entity_type=EntityType.TASK,
                                    parent_id=obj_ms_created_plan_db.entity_id,
                                    suggested_start_time=obj_user_profile.plan[i].activities[j].suggested_time,
                                    suggestion_duration=obj_user_profile.plan[i].activities[j].suggested_duration,
                                    status_id=1,
                                    source_id=0,
                                    entity_desc=obj_user_profile.plan[i].activities[j].daily_objective)
                        
                    obj_d_created_plan_db = await insert_created_plan(obj_d_created_plan,db)
                    message_detail[str(obj_d_created_plan_db.entity_id)] = obj_d_created_plan_db.entity_desc
                    obj_created_plan.append(obj_d_created_plan_db)

                    for k in range(len( obj_user_profile.plan[i].activities[j].activity_detail)):

                        activity_sequence_id = day_sequence_id + (k+1)
                        activity_description, activity_time, activity_duration = await parse_activity(obj_user_profile.plan[i].activities[j].activity_detail[k].activity)
                        obj_activity_created_plan = ICreatedPlan(plan_id=obj_user_plan_db.plan_id,
                                sequence_id= activity_sequence_id,
                                level_id=Level.LEAF,
                                entity_type=EntityType.ACTIVITY,
                                parent_id=obj_d_created_plan_db.entity_id,
                                suggested_start_time= activity_time, #obj_user_profile.plan[i].suggested_time,
                                suggestion_duration=activity_duration, #obj_user_profile.plan[i].suggested_duration,
                                status_id=1,
                                source_id=0,
                                entity_desc=activity_description) #obj_user_profile.plan[i].activity_detail[k].activity)
                    
                        obj_activity_created_plan_db = await insert_created_plan(obj_activity_created_plan,db)
                        message_detail[str(obj_activity_created_plan_db.entity_id)] = obj_activity_created_plan_db.entity_desc            
                        obj_created_plan.append(obj_activity_created_plan_db)


        if obj_user_profile.routine_summary is not None:
            for i in range(len(obj_user_profile.routine_summary.summary_item)):
                #obj_rs = RoutineSummary(summary_item=obj_user_profile.routine_summary[i].summary_item)
                res = await insert_plan_routine_summary(obj_user_plan_ux.plan_id, obj_user_profile.routine_summary.summary_item[i],db )
        if obj_user_profile.general_recommendation_guideline is not None:
            for i in range(len(obj_user_profile.general_recommendation_guideline.general_descripton)):
                #obj_gg = GeneralRecommendationAndGuidelines(general_descripton=obj_user_profile.general_recommendation_guideline[i].general_descripton)
                res = await insert_general_guideline(obj_user_plan_ux.plan_id, obj_user_profile.general_recommendation_guideline.general_descripton[i], db)
        obj_prompt_response_for_user = PlanDetailForUserManagement(
                                                                plan_header= obj_user_plan_ux,
                                                                routine_summary= obj_user_profile.routine_summary,
                                                                general_recommendation_guideline = obj_user_profile.general_recommendation_guideline,
                                                                created_plan=obj_created_plan,
                                                                plan_trail= None
                                                                   )
        message["detail"] = message_detail
        message["task_type"] = "get_serp_for_plan"
        await publish_message(message, msg_connection)
        return obj_prompt_response_for_user
    
    except IntegrityException as e:
        logger.error(f"Some integrity error at the db level when loading the plan from the prompt: {str(e)}")
        raise IntegrityException(
            f"Some integrity error at the db level when loading the plan from the prompt: {str(e)}",
            context = {"detail": f"Some integrity error at the db level when loading the plan from the prompt: {str(e)}"}
        )
    except GeneralDataException as e:
        logger.error(f"Database error when loading the plan from the prompt: {str(e)}")
        raise GeneralDataException(
            f"Database error when loading the plan from the prompt: {str(e)}",
            context={"detail": f"Database error when loading the plan from the prompt: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Unexpected error when loading the plan from the prompt: {str(e)}")
        raise GeneralDataException(
            f"Unexpected error when loading the plan from the prompt: {str(e)}",
            context={"detail" : f"Unexpected error when loading the plan from the prompt: {str(e)}"}
        )


async def process_user_plan_prompt(obj_user_prompt: UXUserPromptInfo,
                                    db: AsyncSession, 
                                    current_user: User,
                                    msg_connection: aio_pika.RobustConnection
                                    ) -> Optional[PlanDetailForUserManagement]:
    try:
        
        params: Dict = {
            "is_active": True,
            "prompt_type": 'primary'
        }
        
        
        print ("The user email is ", current_user.first_name)
        prompt = await get_prompt_metadata(params, db)

        if not prompt:
            logger.error("No active primary prompt found in database")
            raise GeneralDataException(
                message= f"prompt text is missing the db",
                context="System configuration error: No active primary prompt found"
            )
        prompt_text = None
        session_id = None
        root_id = None
        new_context = False
        q_client = QdrantClient()
        hsh_result = {}

        if obj_user_prompt.prev_plan_id:
            if not obj_user_prompt.root_id:
                raise GeneralDataException(message= f"Need both plan id and root id",
                                           context= f"root id is missing")
            if await count_words_alpha_numeric(obj_user_prompt.prompt_text) < 3:
                raise NotEnoughInfoToGenerateGoal(
                            reason=f"We need more information to generate the goal",
                            prompt_text=f" {obj_user_prompt.prompt_text}"
                        )
            filter_params = {}
            filter_params["root_id"] = obj_user_prompt.root_id
            filter_params["intent"] = "calc"
            obj_goal_result =await get_goal_builder(filter_params, db)
            historic_prompt_text = None
            if len(obj_goal_result) > 0 :
                for i in range(len(obj_goal_result)):
                    
                    if i == 0 :
                        historic_prompt_text = obj_goal_result[i].prompt_text
                        session_id = str(obj_goal_result[i].session_id)
                        root_id = str(obj_goal_result[i].root_id)
                    else:
                        historic_prompt_text = f"{historic_prompt_text} {obj_goal_result[i].prompt_text}"


                if random.random() < 0.5:
                    hsh_result = await detect_context_switch_gemini(obj_user_prompt.prompt_text, historic_prompt_text)
                else:
                    hsh_result = await detect_context_switch(obj_user_prompt.prompt_text, historic_prompt_text)

                if hsh_result:
                    if "context_switch" not in hsh_result:
                        logger.error("We have an issue with the response for detecting context change")
                        raise PlanContextChange(
                            prompt_text="Trying to assess if the request is part of the same context {obj_user_prompt.prompt_text}",
                            reason = "Potential context switch"
                    
                        )
                    '''
                    {
                        "context_switch": true,
                        "reason": "The new prompt is about flying, which is unrelated to weight loss.",
                        "unsafe": true,
                        "unsafe_reason": "The prompt includes language related to criminal activity.",
                        "unsupported_domain": true,
                        "domain_reason": "Flying an airplane is not part of the supported domains."
                    }
                    '''


                    if hsh_result["unsafe"] == True:
                        raise PlanIllegalText(
                            reason=f"Unsafe language in the prompt text",
                            prompt_text=f"Prompt text seems to have unsage language {obj_user_prompt.prompt_text}"
                        )
                    if hsh_result["context_switch"] == True:
                        raise PlanContextChange(
                            reason=f"You changed the context",
                            prompt_text=f"You have moved away from the original goal and it seems new {obj_user_prompt.prompt_text}"
                        )
                        session_id = str(uuid.uuid4())
                        concatenated_prompt = obj_user_prompt.prompt_text
                        obj_user_prompt.prev_plan_id = None
                        prompt_text = obj_user_prompt.prompt_text
                        new_context = True
                    else:
                        prompt_text = f"{historic_prompt_text} {obj_user_prompt.prompt_text}"
                        concatenated_prompt = prompt_text
                else:
                    #This should never happen
                    prompt_text = f"{historic_prompt_text} {obj_user_prompt.prompt_text}"
                    hsh_result["revised_summary"] = None
                    concatenated_prompt = prompt_text
            else:
                #This could happen when the input is wrong or there is data corruption
                raise GeneralDataException(
                            message=f"Unable to find a row with the root id {obj_user_prompt.root_id}",
                            context={"detail": f"Unable to find a row with the root id {obj_user_prompt.root_id}"}
                )
        else:
            session_id = str(uuid.uuid4())
            obj_user_prompt.prev_plan_id = None
            prompt_text = obj_user_prompt.prompt_text
            new_context = True
            hsh_result["revised_summary"] = None
            concatenated_prompt = obj_user_prompt.prompt_text
        
        if prompt_text is None:
            raise GeneralDataException(
                f"For some reason the prompt_text is empty... quitting",
                context={"detail": f"prompt text is empty. something is off"}
            )
        if await count_words_alpha_numeric(obj_user_prompt.prompt_text) < 5:
            raise NotEnoughInfoToGenerateGoal(
                            reason=f"We need more information to generate the goal",
                            prompt_text=f" {obj_user_prompt.prompt_text}"
                        )
        logger.info(f"The prompt text is {prompt_text}")
        logger.info(f"Prompt guideline is {prompt.prompt_detail}")
        logger.info(f"Prompt version is {prompt.prompt_version}")
        # Initialize OpenAI client
        client = OpenAI(api_key=settings.OPEN_AI_API_KEY)
        #print ("The prompt context is ", prompt.prompt_detail)
        print ("User prompt is ", prompt_text)
        # Attempt API request
        llm_source = None

        
        if random.random() < 0.5:
            # Assuming settings.GOOGLE_API_KEY is set
            genai.configure(api_key=settings.GOOGLE_GEMINI_API_KEY)
            #available_models = genai.list_models()
            '''
            print("Available models:")
            for m in available_models:
                print(f"- {m.name}, supports: {m.supported_generation_methods}")
            # Load the Gemini Pro model (or another suitable Gemini model)
            #model = genai.GenerativeModel('gemini-pro')
            '''
            model = genai.GenerativeModel(model_name='models/gemini-2.0-flash')
            print("User prompt is ", prompt_text)
            prompt_with_context = f"{prompt.prompt_detail_gemini}\n\n{prompt_text}"
            response = model.generate_content(
                prompt_with_context,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=10000,
                    temperature=0.1,
                    top_p=0.3,
                ),
            )
            llm_output = response.text
            #response_content = await generate_gemini_response(prompt.prompt_detail_gemini, prompt_text)
            llm_source = "gemini"
        else:
            llm_source = "chatgpt"
            completion =  client.beta.chat.completions.parse(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompt.prompt_detail_gemini},
                    {"role": "user", "content": prompt_text},
                ],
                max_tokens=15000,
                temperature=0.1,
                top_p=0.3,
                response_format={"type": "json_object"}  # request raw JSON
                #response_format=UserPromptResponse
            )
            llm_output = completion.choices[0].message.content

        response_content = await generate_response(llm_output)

        #print(completion.choices[0].message.content)
        # Extract response content
        #response_content = completion.choices[0].message.parsed
        logger.info(f"The response content is {response_content}")
        logger.info (f"LLM Reason is {response_content.LLMReason}")
            

        if not response_content.plan or len(response_content.plan) <= 0:
            raise GeneralDataException(
                message = f"No data returned for the prompt by AI {prompt_text}",
                context={"detail": f"May be ill formed prompt. no data returned {prompt_text} and the reason is {response_content.LLMReason}"}
            )
        logger.info(f"We have the response content to load in the database")
        
        obj_result = await load_plan(response_content, db, current_user,msg_connection, obj_user_prompt.root_id, obj_user_prompt.prev_plan_id)

        if not uuid.UUID(session_id):
            raise GeneralDataException(
                f"session id cannot be null {session_id} in plan creation",
                context={"detail" : f"session id is null {session_id} in plan creation"}
            )
        if new_context:
            root_id = str(obj_result.plan_header.plan_id)
        obj_goal_step = UXGoalBuilder(plan_id= obj_result.plan_header.plan_id, 
                                        prev_plan_id=obj_user_prompt.prev_plan_id,
                                        prompt_text= obj_user_prompt.prompt_text,
                                        plan_name = obj_result.plan_header.plan_name,
                                        session_id=session_id,
                                        root_id=root_id,
                                        revised_prompt_summary= hsh_result["revised_summary"],
                                        llm_source = llm_source,
                                        user_id=current_user.user_id,
                                        concatenated_prompt=concatenated_prompt,
                                        created_dt=None
                                        )
        
        obj_insert_goal = await insert_goal_builder(obj_goal_step, db)
        await upsert_message(obj_user_prompt.prompt_text, session_id, obj_result.plan_header.plan_id, q_client)
        #final_output = obj_result.plan_trail = obj_goal_step
        final_output = obj_result.model_copy(update={'plan_trail':obj_goal_step})
        return final_output

    except OpenAIError as e:
        logger.error(f"OpenAI API Error: {e}")
        raise e

    except requests.exceptions.RequestException as e:
        raise GeneralDataException(
            f"Possible network issue when processing prompt {str(e)}",
            context={"detail": f"Possible network issue {str(e)}"}
        )

    except ValueError as e:
        raise GeneralDataException(
            f"Possible value issue when processing prompt  {str(e)}",
            context={"detail": f"Possible value issue from openAI {str(e)}"}
        )
        logger.error(f"Response Error: {e}")
    except IntegrityException as e:
        logger.error(f"IntegrityError when when processing prompt : {str(e)}")
        raise IntegrityException(
            f"IntegrityError when when processing prompt : {str(e)}",
            context = {"detail": f"IntegrityError when when processing prompt : {str(e)}"}
        )
    except GeneralDataException as e:
        logger.error(f"Database error when processing prompt: {str(e)}")
        raise GeneralDataException(
            f"Database error when processing prompt: {str(e)}",
            context={"detail": f"Database error when processing prompt: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Some general error occured  when processing prompt: {str(e)}")
        raise GeneralDataException(
            f"Some general error occured  when processing prompt: {str(e)}",
            context = { "detail": f"Some general error occured  when processing prompt: {str(e)}"})

        

async def create_user_plan(user_input: UserPlan, db: AsyncSession):
    """
    Create a new user plan in the database.
    
    Args:
        user_input: The user plan data to insert
        
    Returns:
        The created user plan
        
    Raises:
        HTTPException: For various error conditions
    """
    try:
        if not user_input:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User plan data is required"
            )
            
        try:
            result = await user_plan.insert_plan( user_input, db)
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create user plan"
                )
            return result
            
        except SQLAlchemyError as e:
            logger.error(f"Database error when inserting user plan: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error occurred while creating user plan"
            )
            
    except HTTPException:
        # Re-raise HTTP exceptions to maintain their status codes and details
        raise
    except Exception as e:
        logger.error(f"Unexpected error in create_user_plan: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the user plan"
        )

async def get_embedding(client: OpenAI, text: str):
    response = client.embeddings.create(
        input=text,
        model="text-embedding-ada-002"
    )
    return response.data[0].embedding
    
async def find_relevance(text: str,  q_client: QdrantClient, session_id: str):
    try:
        ai_client = OpenAI(api_key=settings.OPEN_AI_APIKEY)
        # Define collection name
        collection_name = settings.QDRANT_GOAL_BUILDER_COLLECTION_NAME
        exists = await q_client.collection_exists(collection_name)
    # Create collection (if not exists)
        if not exists:
                await q_client.create_collection(
                collection_name=collection_name,
                    vectors_config=VectorParams(size=len( await get_embedding(ai_client, "test")), distance=Distance.COSINE)
                )   
                logger.info(f"Creating the goal builder collection {collection_name}")
        top_k = 100
        search_result = await q_client.search(
            collection_name=collection_name,
            query_vector= await get_embedding(ai_client, text),
            limit=top_k,
            query_filter=Filter(
                must=[
                    FieldCondition(key="session_id", match=MatchValue(value=session_id))
                ]
            )
        )

        return search_result

    except Exception as e:
        logger.error (f" Error in find relevance function {str(e)}")
        raise GeneralDataException(
            message="Error in retrieving data from the vector store",
            context= {"detail": f"trying to get supplement data for {text}"}
        )

async def upsert_message(message: str, session_id: str, plan_id: str, q_client: QdrantClient):
    try:
        ai_client = OpenAI(api_key=settings.OPEN_AI_API_KEY)

        collection_name = settings.QDRANT_GOAL_BUILDER_COLLECTION_NAME

        exists = await q_client.collection_exists(collection_name)
        # Create collection (if not exists)
        if not exists:
            await q_client.create_collection(
                    collection_name=collection_name,
                        vectors_config=VectorParams(size=len(await get_embedding(ai_client, "test")), distance=Distance.COSINE)
                    )   
            logger.info(f"Creating the goal builder collection {collection_name}")

        embedding = await get_embedding(ai_client,message)
        await q_client.upsert(
            collection_name=collection_name,
            points=[
                PointStruct(
                    id=plan_id,
                    vector=embedding,
                    payload={
                        "text": message,
                        "session_id": session_id
                    }
                )
            ]
        )
    except Exception as e:
        logger.error(f"Error in qdrant upsert function {str(e)}")
        raise GeneralDataException(
            message="Error in retrieving data from the vector store",
            context= {"detail": f"trying to get supplement data for {message}"}
        )
    


async def extract_json_from_string(response_text: str) -> str:
    """
    Removes leading `````` from a Gemini response,
    returning the inner JSON string.
    """
    # Remove leading and trailing whitespace
    cleaned = response_text.strip()
    # Remove leading `````` if present
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):].lstrip("\n")
    elif cleaned.startswith("```"):
        cleaned = cleaned[len("```"):].lstrip("\n")
    # Remove trailing ```
    if cleaned.endswith("```"):
        cleaned = cleaned[:-len("```")].rstrip()
    return cleaned


# Your Pydantic classes (as defined previously) remain the same

async def generate_gemini_response(prompt_detail, prompt_text):
    # Assuming settings.GOOGLE_API_KEY is set
    genai.configure(api_key=settings.GOOGLE_GEMINI_API_KEY)
    #available_models = genai.list_models()
    '''
    print("Available models:")
    for m in available_models:
        print(f"- {m.name}, supports: {m.supported_generation_methods}")
# Load the Gemini Pro model (or another suitable Gemini model)
    #model = genai.GenerativeModel('gemini-pro')
    '''
    model = genai.GenerativeModel(model_name='models/gemini-2.0-flash')
    print("User prompt is ", prompt_text)
    try:
        prompt_with_context = f"{prompt_detail}\n\n{prompt_text}"
        response = model.generate_content(
            prompt_with_context,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=15000,
                temperature=0.1,
                top_p=0.3,
            ),
        )
        gemini_content = response.text

        print("Gemini Raw Output:", gemini_content)  # For debugging

        try:
            cleansed_data = await extract_json_from_string(gemini_content)
            print("Parsed JSON:", cleansed_data)
            parsed_data = json.loads(cleansed_data)
            # Extract plan-level information
            plan_level_data = {
                "gender": parsed_data.get("gender"),
                "weight": parsed_data.get("weight"),
                "height": parsed_data.get("height"),
                "Age": parsed_data.get("Age"),
                "PreExistingCondition": parsed_data.get("PreExistingCondition"),
                "PriorExpertise": parsed_data.get("PriorExpertise"),
                "Occupation": parsed_data.get("Occupation"),
                "Goal": parsed_data.get("Goal"),
                "ExplicitAskForGoal": parsed_data.get("ExplicitAskForGoal"),
                "GoalDuration": parsed_data.get("GoalDuration"),
                "WorkHours": parsed_data.get("WorkHours"),
                "IsWorkingFlag": parsed_data.get("IsWorkingFlag"),
                "UserQuery": parsed_data.get("UserQuery"),
                "LLMReason": parsed_data.get("LLMReason"),
                "plan_name": parsed_data.get("plan_name"),
                "plan_type": parsed_data.get("plan_type"),
                "plan_category": parsed_data.get("PlanCategory"),
            }



            # Handle the "plan" node based on plan_type
            plan_type = parsed_data.get("plan_type")
            plan_data = parsed_data.get("plan", [])
            mapped_plan = []

            if plan_type == "Weekly":
                for item in plan_data:
                    mapped_plan.append(WeeklyPlanWithDailyDetail.model_validate(item))
            elif plan_type == "Daily":
                for item in plan_data:
                    mapped_plan.append(ActivityByDayDetail.model_validate(item))
            else:
                for item in plan_data:
                    mapped_plan.append(MileStone.model_validate(item))

            plan_level_data["plan"] = mapped_plan

                        # Handle optional routine_summary
            if "routine_summary" in parsed_data:
                routine_summary = RoutineSummary(summary_item=parsed_data["routine_summary"]["summary"])
                plan_level_data["routine_summary"] = routine_summary

            # Handle optional general_recommendation_guideline
            if "general_recommendation_guideline" in parsed_data:
                general_description = GeneralRecommendationAndGuidelines(general_descripton=parsed_data["general_recommendation_guideline"]["general_description"])
                plan_level_data["general_recommendation_guideline"] = general_description

            # Validate the complete structure
            user_response = UserPromptResponse.model_validate(plan_level_data)
            print("Parsed Response:", user_response.model_dump_json(indent=2)) # For detailed output
            return user_response

        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from Gemini output: {e}")
            logger.error(f"Problematic JSON: {gemini_content}")
            raise GeneralDataException(
                message=f"Error decoding JSON from Gemini output: {e}",
                context={"detail": f"Error decoding JSON from Gemini output: {e}"}
            )
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            logger.error(f"An unexpected error occurred: {e}")
            raise GeneralDataException(
                message=f"An unexpected error occurred: {e}",
                context={"detail": f"An unexpected error occurred: {e}"}
            )

    except Exception as e:
            logger.error(f"An unexpected error occurred with Gemini API Call: {e}")
            raise GeneralDataException(
                message=f"An unexpected error occurred with Gemini API Call: {e}",
                context={"detail": f"An unexpected error occurred with Gemini API Call: {e}"}
            )


async def generate_response(response_text):
    try:
        cleansed_data = await extract_json_from_string(response_text)
        print("Parsed JSON:", cleansed_data)
        parsed_data = json.loads(cleansed_data)
        # Extract plan-level information
        plan_level_data = {
            "gender": parsed_data.get("gender"),
            "weight": parsed_data.get("weight"),
            "height": parsed_data.get("height"),
            "Age": parsed_data.get("Age"),
            "PreExistingCondition": parsed_data.get("PreExistingCondition"),
            "PriorExpertise": parsed_data.get("PriorExpertise"),
            "Occupation": parsed_data.get("Occupation"),
            "Goal": parsed_data.get("Goal"),
            "ExplicitAskForGoal": parsed_data.get("ExplicitAskForGoal"),
            "GoalDuration": parsed_data.get("GoalDuration"),
            "WorkHours": parsed_data.get("WorkHours"),
            "IsWorkingFlag": parsed_data.get("IsWorkingFlag"),
            "UserQuery": parsed_data.get("UserQuery"),
            "LLMReason": parsed_data.get("LLMReason"),
            "plan_name": parsed_data.get("plan_name"),
            "plan_type": parsed_data.get("plan_type"),
            "plan_category": parsed_data.get("PlanCategory"),
        }



        # Handle the "plan" node based on plan_type
        plan_type = parsed_data.get("plan_type")
        plan_data = parsed_data.get("plan", [])
        mapped_plan = []

        if plan_type == "Weekly":
            for item in plan_data:
                mapped_plan.append(WeeklyPlanWithDailyDetail.model_validate(item))
        elif plan_type == "Daily":
            for item in plan_data:
                mapped_plan.append(ActivityByDayDetail.model_validate(item))
        else:
            for item in plan_data:
                mapped_plan.append(MileStone.model_validate(item))

        plan_level_data["plan"] = mapped_plan

                    # Handle optional routine_summary
        if "routine_summary" in parsed_data:
            routine_summary = RoutineSummary(summary_item=parsed_data["routine_summary"]["summary"])
            plan_level_data["routine_summary"] = routine_summary

        # Handle optional general_recommendation_guideline
        if "general_recommendation_guideline" in parsed_data:
            general_description = GeneralRecommendationAndGuidelines(general_descripton=parsed_data["general_recommendation_guideline"]["general_description"])
            plan_level_data["general_recommendation_guideline"] = general_description

        # Validate the complete structure
        user_response = UserPromptResponse.model_validate(plan_level_data)
        print("Parsed Response:", user_response.model_dump_json(indent=2)) # For detailed output
        return user_response

    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from Gemini output: {e}")
        logger.error(f"Problematic JSON: {response_text}")
        raise GeneralDataException(
            message=f"Error decoding JSON from Gemini output: {e}",
            context={"detail": f"Error decoding JSON from Gemini output: {e}"}
        )
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        logger.error(f"An unexpected error occurred: {e}")
        raise GeneralDataException(
            message=f"An unexpected error occurred: {e}",
            context={"detail": f"An unexpected error occurred: {e}"}
        )



async def get_prompt_history_svc(filter_params: dict, db: AsyncSession, current_user: User) -> Optional[UXGoalBuilder]:

    try:
        filter_params["intent"] = "display"
        filter_params["user_id"] = current_user.user_id
        ret = await get_goal_builder(filter_params,db)
        res = []
        for item in ret:
            res.append(UXGoalBuilder.model_validate(item))
        return res
    except ValueError as e:
        logger.error(f"Response Error in get_prompt_history_svc: {e}")
        raise GeneralDataException(
            f"Possible value issue when processing prompt  {str(e)}",
            context={"detail": f"Possible value issue from openAI {str(e)}"}
        )

    except IntegrityException as e:
        logger.error(f"IntegrityError when when processing prompt : {str(e)}")
        raise IntegrityException(
            f"IntegrityError when when processing prompt : {str(e)}",
            context = {"detail": f"IntegrityError when when processing prompt : {str(e)}"}
        )
    except GeneralDataException as e:
        logger.error(f"Database error when processing prompt: {str(e)}")
        raise GeneralDataException(
            f"Database error when processing prompt: {str(e)}",
            context={"detail": f"Database error when processing prompt: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Some general error occured  when processing prompt: {str(e)}")
        raise GeneralDataException(
            f"Some general error occured  when processing prompt: {str(e)}",
            context = { "detail": f"Some general error occured  when processing prompt: {str(e)}"})

'''
async def load_plan(obj_user_profile: UserPromptResponse, 
                    db: AsyncSession, 
                    current_user: User,
                    msg_connection: aio_pika.RobustConnection):
    try:

        plan_item = []
        obj_weekly_objective_user = []
        obj_daily_objective_user = []
        obj_activities_user = []
        obj_created_plan = []
        message = {}
        message_detail = {}
        logger.info(f"Inserting the user plan for user {current_user.user_id}")
        obj_user_plan = UserPlan(user_id= current_user.user_id,
                                 plan_name = obj_user_profile.plan_name,
                                 plan_type = obj_user_profile.plan_type,
                                 plan_goal = obj_user_profile.Goal)

    # Perform database operations

        obj_user_plan_db = await user_plan.insert_plan( obj_user_plan, db)
        message["plan_id"] = str(obj_user_plan_db.plan_id)
        message["user_id"] = str(obj_user_plan_db.user_id)
        obj_user_plan_ux = UXUserPlanIdentifier(user_id = str(obj_user_plan_db.user_id),
                                              plan_id = str(obj_user_plan_db.plan_id),
                                              plan_name = obj_user_plan_db.plan_name,
                                              plan_type = obj_user_plan_db.plan_type,
                                              plan_goal = obj_user_plan_db.plan_goal,
                                              plan_end_date= obj_user_plan_db.plan_end_date,
                                              plan_start_date= obj_user_plan_db.plan_start_date)
        if not obj_user_plan_db:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user plan"
            )      
        logger.info(f"User plan is successfully inserted and the plan id is {obj_user_plan_db.plan_id}")
        if obj_user_profile.plan_type == "Weekly":
            print ("The number of week count is ", len(obj_user_profile.plan))
            for i in range(len(obj_user_profile.plan)):
                week_sequence_id = (i+1)*10000
                obj_wk_created_plan = ICreatedPlan(plan_id=obj_user_plan_db.plan_id,
                                                sequence_id= week_sequence_id,
                                                level_id=Level.ROOT,
                                                entity_type=EntityType.WEEK,
                                                parent_id=None,
                                                suggested_start_time=None,
                                                suggestion_duration=None,
                                                status_id=1,
                                                source_id=0,
                                                entity_desc=obj_user_profile.plan[i].weekly_objective)
                obj_wk_created_plan_db = await insert_created_plan(obj_wk_created_plan,db)
                obj_created_plan.append(obj_wk_created_plan_db)
                message_detail[str(obj_wk_created_plan_db.entity_id)] = obj_wk_created_plan_db.entity_desc


                obj_week_header = WeeklyPlanIdentifier(week_text= obj_user_profile.plan[i].week_text,
                                                    weekly_objective= obj_user_profile.plan[i].weekly_objective,
                                                    plan_id = obj_user_plan_db.plan_id,
                                                    week_objective_sequence = i,
                                                    week_number= obj_user_profile.plan[i].week_number)

                obj_week_header_db = await insert_weekly_header(obj_week_header, db)
                message_detail[str(obj_week_header_db.entity_id)] = obj_week_header_db.week_objective
                obj_weekly_objective_user.append(obj_week_header)

                for j in range(len(obj_user_profile.plan[i].dailyactivity)):
                    day_sequence_id = week_sequence_id + (j+1)*100
                    obj_d_created_plan = ICreatedPlan(plan_id=obj_user_plan_db.plan_id,
                                sequence_id= day_sequence_id,
                                level_id=Level.BRANCH,
                                entity_type=EntityType.DAY,
                                parent_id=obj_wk_created_plan_db.entity_id,
                                suggested_start_time=obj_user_profile.plan[i].dailyactivity[j].suggested_time,
                                suggestion_duration=obj_user_profile.plan[i].dailyactivity[j].suggested_duration,
                                status_id=1,
                                source_id=0,
                                entity_desc=obj_user_profile.plan[i].dailyactivity[j].daily_objective)
                    
                    obj_d_created_plan_db = await insert_created_plan(obj_d_created_plan,db)
                    message_detail[str(obj_d_created_plan_db.entity_id)] = obj_d_created_plan_db.entity_desc
                    obj_created_plan.append(obj_d_created_plan_db)

                    obj_day_header = ActivityByDayIdentifier(day_text = obj_user_profile.plan[i].dailyactivity[j].day_text,
                                                            daily_objective = obj_user_profile.plan[i].dailyactivity[j].daily_objective,
                                                            week_number= obj_week_header_db.week_number,
                                                            day_number= obj_user_profile.plan[i].dailyactivity[j].day_number,
                                                            plan_id = obj_user_plan_db.plan_id,
                                                            day_objective_sequence= j,
                                                            week_objective_sequence= i,
                                                            suggested_time= obj_user_profile.plan[i].dailyactivity[j].suggested_time,
                                                            suggested_duration= obj_user_profile.plan[i].dailyactivity[j].suggested_duration
                                                            )


                    obj_day_header_db = await insert_daily_header(obj_day_header, db)
                    message_detail[str(obj_day_header_db.entity_id)] = obj_day_header_db.day_objective
                    obj_daily_objective_user.append(obj_day_header)

                    for k in range(len( obj_user_profile.plan[i].dailyactivity[j].activity_detail)):

                        activity_sequence_id = day_sequence_id + (k+1)
                        obj_activity_created_plan = ICreatedPlan(plan_id=obj_user_plan_db.plan_id,
                                sequence_id= activity_sequence_id,
                                level_id=Level.LEAF,
                                entity_type=EntityType.ACTIVITY,
                                parent_id=obj_d_created_plan_db.entity_id,
                                suggested_start_time=obj_user_profile.plan[i].dailyactivity[j].suggested_time,
                                suggestion_duration=obj_user_profile.plan[i].dailyactivity[j].suggested_duration,
                                status_id=1,
                                source_id=0,
                                entity_desc=obj_user_profile.plan[i].dailyactivity[j].activity_detail[k].activity)
                    
                        obj_activity_created_plan_db = await insert_created_plan(obj_activity_created_plan,db)
                        message_detail[str(obj_activity_created_plan_db.entity_id)] = obj_activity_created_plan_db.entity_desc
                        obj_created_plan.append(obj_activity_created_plan_db)

                        obj_activity = ActivityDetail(activity= obj_user_profile.plan[i].dailyactivity[j].activity_detail[k].activity,
                                                        suggest_time= obj_user_profile.plan[i].dailyactivity[j].suggested_time,
                                                        suggest_duration= obj_user_profile.plan[i].dailyactivity[j].suggested_duration,
                                                        plan_id = obj_user_plan_db.plan_id,
                                                        day_number= obj_day_header_db.day_number,
                                                        week_number= obj_week_header_db.week_number,
                                                        week_objective_sequence= i,
                                                        day_objective_sequence= j,
                                                        activity_sequence= k)
                        obj_activity_db = await insert_activity_detail(obj_activity, db)
                        message_detail[str(obj_activity_db.activity_id)] = obj_activity_db.activity
                        # Convert SQLAlchemy object to dict
                        obj_x = ActivityDetailIdentifier(
                            plan_id = str(obj_activity_db.plan_id),
                            week_number = obj_activity_db.week_number,
                            day_number= obj_activity_db.day_number,
                            suggest_time= obj_activity_db.suggest_time,
                            suggest_duration= obj_activity_db.suggest_duration,
                            activity_sequence= obj_activity_db.activity_sequence,
                            week_objective_sequence= obj_activity_db.week_objective_sequence,
                            day_objective_sequence= obj_activity_db.day_objective_sequence,
                            activity_id= str(obj_activity_db.activity_id),
                            activity= obj_activity_db.activity
                        )
                        
                        obj_activities_user.append(obj_x)

        elif obj_user_profile.plan_type == "Daily":
            for i in range(len(obj_user_profile.plan)):
                day_sequence_id = (i+1)*10000
                obj_d_created_plan = ICreatedPlan(plan_id=obj_user_plan_db.plan_id,
                                sequence_id= day_sequence_id,
                                level_id=Level.ROOT,
                                entity_type=EntityType.DAY,
                                parent_id=None,
                                suggested_start_time=obj_user_profile.plan[i].suggested_time,
                                suggestion_duration=obj_user_profile.plan[i].suggested_duration,
                                status_id=1,
                                source_id=0,
                                entity_desc=obj_user_profile.plan[i].daily_objective)
                    
                obj_d_created_plan_db = await insert_created_plan(obj_d_created_plan,db)
                message_detail[str(obj_d_created_plan_db.entity_id)] = obj_d_created_plan_db.entity_desc
                obj_created_plan.append(obj_d_created_plan_db)
                obj_day_header = ActivityByDayIdentifier(day_text = obj_user_profile.plan[i].day_text,
                                                         day_number= obj_user_profile.plan[i].day_number,
                                                            daily_objective = obj_user_profile.plan[i].daily_objective,
                                                            week_number= 0,
                                                            plan_id = obj_user_plan_db.plan_id,
                                                            day_objective_sequence= i,
                                                            week_objective_sequence= 0,
                                                            suggested_time=obj_user_profile.plan[i].suggested_time,
                                                            suggested_duration=obj_user_profile.plan[i].suggested_duration
                                                            )
                obj_day_header_db = await insert_daily_header(obj_day_header, db)
                message_detail[str(obj_day_header_db.entity_id)] = obj_day_header_db.day_objective
                obj_daily_objective_user.append(obj_day_header)
                for k in range(len( obj_user_profile.plan[i].activity_detail)):

                    activity_sequence_id = day_sequence_id + (k+1)
                    obj_activity_created_plan = ICreatedPlan(plan_id=obj_user_plan_db.plan_id,
                            sequence_id= activity_sequence_id,
                            level_id=Level.LEAF,
                            entity_type=EntityType.ACTIVITY,
                            parent_id=obj_d_created_plan_db.entity_id,
                            suggested_start_time=obj_user_profile.plan[i].dailyactivity[j].suggested_time,
                            suggestion_duration=obj_user_profile.plan[i].dailyactivity[j].suggested_duration,
                            status_id=1,
                            source_id=0,
                            entity_desc=obj_user_profile.plan[i].dailyactivity[j].activity_detail[k].activity)
                
                    obj_activity_created_plan_db = await insert_created_plan(obj_activity_created_plan,db)
                    message_detail[str(obj_activity_created_plan_db.entity_id)] = obj_activity_created_plan_db.entity_desc
                    obj_created_plan.append(obj_activity_created_plan_db)

                    obj_activity = ActivityDetail(activity= obj_user_profile.plan[i].activity_detail[k].activity,
                                                        suggest_time= obj_user_profile.plan[i].suggested_time,
                                                        suggest_duration= obj_user_profile.plan[i].suggested_duration,
                                                        plan_id = obj_user_plan_db.plan_id,
                                                        day_number= obj_user_profile.plan[i].day_number,
                                                        week_number= 0,
                                                        week_objective_sequence= 0,
                                                        day_objective_sequence= i,
                                                        activity_sequence = k
                                                        )
                    
                    obj_activity_db = await insert_activity_detail(obj_activity, db)
                    message_detail[str(obj_activity_db.activity_id)] = obj_activity_db.activity
                    obj_x = ActivityDetailIdentifier(
                            plan_id = str(obj_activity_db.plan_id),
                            week_number = obj_activity_db.week_number,
                            day_number= obj_activity_db.day_number,
                            suggest_time= obj_activity_db.suggest_time,
                            suggest_duration=obj_activity_db.suggest_duration,
                            activity_sequence= obj_activity_db.activity_sequence,
                            week_objective_sequence= obj_activity_db.week_objective_sequence,
                            day_objective_sequence= obj_activity_db.day_objective_sequence,
                            activity_id= obj_activity_db.activity_id,
                            activity= obj_activity_db.activity
                        )
                    obj_activities_user.append(obj_x)
        else:
            print ("This is a plan request with no time criteria")
            magic_day_number_constant = "Day-0"
            for i in range(len(obj_user_profile.plan)):
                day_sequence_id = (i+1)*10000
                obj_d_created_plan = ICreatedPlan(plan_id=obj_user_plan_db.plan_id,
                                sequence_id= day_sequence_id,
                                level_id=Level.ROOT,
                                entity_type=EntityType.DAY,
                                parent_id=None,
                                suggested_start_time=obj_user_profile.plan[i].suggested_time,
                                suggestion_duration=obj_user_profile.plan[i].suggested_duration,
                                status_id=1,
                                source_id=0,
                                entity_desc=obj_user_profile.plan[i].daily_objective)
                    
                obj_d_created_plan_db = await insert_created_plan(obj_d_created_plan,db)
                message_detail[str(obj_d_created_plan_db.entity_id)] = obj_d_created_plan_db.entity_desc
                obj_created_plan.append(obj_d_created_plan)



                obj_day_header = ActivityByDayIdentifier(day_text = magic_day_number_constant,
                                                         day_number= 0,
                                                            daily_objective = obj_user_profile.plan[i].daily_objective,
                                                            week_number= 0,
                                                            plan_id = obj_user_plan_db.plan_id,
                                                            day_objective_sequence=i,
                                                            week_objective_sequence= 0,
                                                            suggested_time= obj_user_profile.plan[i].suggested_time,
                                                            suggested_duration=obj_user_profile.plan[i].suggested_duration
                                                            )
                obj_day_header_db = await insert_daily_header(obj_day_header, db)
                message_detail[str(obj_day_header_db.entity_id)] = obj_day_header_db.day_objective
                obj_daily_objective_user.append(obj_day_header)
                for k in range(len( obj_user_profile.plan[i].activity_detail)):

                    activity_sequence_id = day_sequence_id + (k+1)
                    obj_activity_created_plan = ICreatedPlan(plan_id=obj_user_plan_db.plan_id,
                            sequence_id= activity_sequence_id,
                            level_id=Level.LEAF,
                            entity_type=EntityType.ACTIVITY,
                            parent_id=obj_d_created_plan_db.entity_id,
                            suggested_start_time=obj_user_profile.plan[i].dailyactivity[j].suggested_time,
                            suggestion_duration=obj_user_profile.plan[i].dailyactivity[j].suggested_duration,
                            status_id=1,
                            source_id=0,
                            entity_desc=obj_user_profile.plan[i].dailyactivity[j].activity_detail[k].activity)
                
                    obj_activity_created_plan_db = await insert_created_plan(obj_activity_created_plan,db)
                    message_detail[str(obj_activity_created_plan_db.entity_id)] = obj_activity_created_plan_db.entity_desc            
                    obj_created_plan.append(obj_activity_created_plan_db)



                    obj_activity = ActivityDetail(activity= obj_user_profile.plan[i].activity_detail[k].activity,
                                                        suggest_time= obj_user_profile.plan[i].suggested_time,
                                                        suggest_duration=obj_user_profile.plan[i].suggested_duration,
                                                        plan_id = obj_user_plan_db.plan_id,
                                                        day_number= 0,
                                                        week_number= 0,
                                                        week_objective_sequence= 0,
                                                        day_objective_sequence= i,
                                                        activity_sequence=  k)
                    obj_activity_db = await insert_activity_detail(obj_activity, db)
                    message_detail[str(obj_activity_db.activity_id)] = obj_activity_db.activity
                    obj_x = ActivityDetailIdentifier(
                            plan_id = str(obj_activity_db.plan_id),
                            week_number = obj_activity_db.week_number,
                            day_number= obj_activity_db.day_number,
                            suggest_time= obj_activity_db.suggest_time,
                            suggest_duration=obj_activity_db.suggest_duration,
                            activity_sequence= obj_activity_db.activity_sequence,
                            week_objective_sequence= obj_activity_db.week_objective_sequence,
                            day_objective_sequence= obj_activity_db.day_objective_sequence,
                            activity_id= str(obj_activity_db.activity_id),
                            activity= obj_activity_db.activity
                        )
                        
                    obj_activities_user.append(obj_x)
        if obj_user_profile.routine_summary is not None:
            for i in range(len(obj_user_profile.routine_summary.summary_item)):
                #obj_rs = RoutineSummary(summary_item=obj_user_profile.routine_summary[i].summary_item)
                res = await insert_plan_routine_summary(obj_user_plan_ux.plan_id, obj_user_profile.routine_summary.summary_item[i],db )
        if obj_user_profile.general_recommendation_guideline is not None:
            for i in range(len(obj_user_profile.general_recommendation_guideline.general_descripton)):
                #obj_gg = GeneralRecommendationAndGuidelines(general_descripton=obj_user_profile.general_recommendation_guideline[i].general_descripton)
                res = await insert_general_guideline(obj_user_plan_ux.plan_id, obj_user_profile.general_recommendation_guideline.general_descripton[i], db)
        obj_prompt_response_for_user = PlanDetailForUserManagement(
                                                                plan_header= obj_user_plan_ux,
                                                                routine_summary= obj_user_profile.routine_summary,
                                                                general_recommendation_guideline = obj_user_profile.general_recommendation_guideline,
                                                                created_plan=obj_created_plan
                                                                   )
        message["detail"] = message_detail
        message["task_type"] = "get_serp_for_plan"
        await publish_message(message, msg_connection)
        return obj_prompt_response_for_user
    
    except IntegrityException as e:
        logger.error(f"Some integrity error at the db level when loading the plan from the prompt: {str(e)}")
        raise IntegrityException(
            f"Some integrity error at the db level when loading the plan from the prompt: {str(e)}",
            context = {"detail": f"Some integrity error at the db level when loading the plan from the prompt: {str(e)}"}
        )
    except GeneralDataException as e:
        logger.error(f"Database error when loading the plan from the prompt: {str(e)}")
        raise GeneralDataException(
            f"Database error when loading the plan from the prompt: {str(e)}",
            context={"detail": f"Database error when loading the plan from the prompt: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Unexpected error when loading the plan from the prompt: {str(e)}")
        raise GeneralDataException(
            f"Unexpected error when loading the plan from the prompt: {str(e)}",
            context={"detail" : f"Unexpected error when loading the plan from the prompt: {str(e)}"}
        )
'''

async def test():
    pass