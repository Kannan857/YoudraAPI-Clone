from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException
from sqlalchemy import update
from datetime import datetime
from app.data.dbinit import get_db
from fastapi import Request
from uuid import UUID
from app.model.progress_mgmt import ProgressUpdateCreate, ProgressUpdateOut, ProgressUpdateSummaryInput
from app.data.progress_mgmt import create_progress_update, get_progress_by_user_entity, get_progress_tracking_by_plan, get_dashboard_summary_sql, calculate_task_delay
from app.data.user_plan import get_plan, get_executable_plan, get_task_change_history, get_plan_change_history
from app.data.progress_mgmt import get_progress_by_user_entity
from typing import List, Optional
from app.data.user import User
from app.common.exception import IntegrityException, TimeZoneException, GeneralDataException
import structlog
from app.common.date_functions import convert_to_user_timezone, convert_user_time_to_utc, format_date_time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
#from app.service.rewards import RewardsService, RewardEarnedResponse
logger = structlog.get_logger()

#async def create_progress_update_svc(db: AsyncSession, update_data: ProgressUpdateCreate, request_metdata: Request, current_user: User, rewards_service: RewardsService):
async def create_progress_update_svc(db: AsyncSession, update_data: ProgressUpdateCreate, request_metdata: Request, current_user: User):

    try:
        res = await create_progress_update(db, update_data, current_user)
        '''
        total_response = RewardEarnedResponse(
            points_earned=0, 
            badges_earned=[], 
            new_total_points=0
        )
        
        if res.plan_progress >= 25.00 and res.plan_progress <= 49.99 :
            milestone_num = 1
        elif res.plan_progress >= 50.0 and res.plan_progress <= 74.99:
            milestone_num = 2
        elif res.plan_progress >= 75.0  and res.plan_progress <= 99.99:
            milestone_num = 3
        milestone_response = await rewards_service.process_milestone_rewards(
                    current_user.user_id, update_data.plan_id, milestone_num
                )
                
        # Combine milestone rewards
        total_response.points_earned += milestone_response.points_earned
        total_response.badges_earned.extend(milestone_response.badges_earned)
        total_response.new_total_points = milestone_response.new_total_points

        if res.plan_progress == 100:
            completion_response = await rewards_service.process_plan_completion_rewards(
                current_user.user_id, update_data.plan_id
            )
            
            # CRITICAL: Combine completion rewards with milestone rewards
            total_response.points_earned += completion_response.points_earned
            total_response.badges_earned.extend(completion_response.badges_earned)
            total_response.new_total_points = completion_response.new_total_points
        '''
        return res
    except IntegrityException as e:

        logger.error(f"IntegrityError when inserting progress update: {str(e)}")
        raise IntegrityException(
            "Integrity error when inserting progress update",
            context = {"detail": "This plan conflicts with an progress update. Possible duplicate entry or foreign key constraint failure."}
        )
    except GeneralDataException as e:

        logger.error(f"Database error when inserting progress update: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the progress update",
            context={"detail": "Database error occurred while inserting progress update"}
        )
    except TimeZoneException as e:
        logger.error(f"Time manipulation error when inserting progress update: {str(e)}")
        raise GeneralDataException(
            f"Time manipulation error when inserting progress update: {str(e)}",
            context={"detail": f"Time manipulation error when inserting progress update: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Unexpected error in insertng progress update: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured while inserting progress update",
            context={"detail" : "An unexpected error occurred while formatting the date in inserting progress update"}
        )


async def get_progress_by_user_entity_svc( db: AsyncSession, current_user: User, entity_id: UUID = None):
    try:
        logger.info(f"User id is {current_user.user_id}")
        user_id = UUID(str(current_user.user_id))
        res = await get_progress_by_user_entity(db, user_id,  entity_id)
        return res
    except IntegrityException as e:

        logger.error(f"Integrity Error while retrieving the progress data: {str(e)}")
        raise IntegrityException(
            "Integrity Error while retrieving the progress data",
            context = {"detail": "Error while retrieving the progress data"}
        )
    except GeneralDataException as e:

        logger.error(f"Database Error while retrieving the progress datan: {str(e)}")
        raise GeneralDataException(
            "Database Error while retrieving the progress data",
            context={"detail": "Database Error while retrieving the progress data"}
        )
    except TimeZoneException as e:
        logger.error(f"Time manipulation  Error while retrieving the progress data: {str(e)}")
        raise GeneralDataException(
            f"Time manipulation Error while retrieving the progress data: {str(e)}",
            context={"detail": f"Time manipulation Error while retrieving the progress data: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Unexpected Error while retrieving the progress data: {str(e)}")
        raise GeneralDataException(
            "Unexpected Error while retrieving the progress data",
            context={"detail" : "An unexpected Error while retrieving the progress data"}
        )


def calculate_goal_discipline_score(plan, total_tasks, completed_tasks, avg_task_moves, plan_move_count, task_delay, plan_delay):
    try:

        if total_tasks <= 0:
            return "N/A"
        if plan_delay < 0:
            return "N/A"
        allowed_task_delay_window = 3
        allowed_plan_delay_window = 10
        allowed_plan_moves = 2
        # Basic scoring out of 100
        score = 100
        score -= (avg_task_moves/total_tasks) * 5  # penalize frequent changes
        score -= (task_delay/allowed_task_delay_window) * 20  # penalize delays
        score -= (plan_delay/allowed_plan_delay_window) * 10
        score -= min(plan_move_count,allowed_plan_moves) * 10
        score += (completed_tasks / total_tasks) * 20  # reward completion
        return round(max(min(score, 100), 0), 2)
    
    except Exception as e:
        logger.error(f"Unexpected Error while calculating gds: {str(e)}")
        raise GeneralDataException(
            "Unexpected Error while calculating gds",
            context={"detail" : "An unexpected Error while calculating gds"}
        )


async def get_plan_dashboard(plan_detail: ProgressUpdateSummaryInput, current_user: User, db: AsyncSession) -> Optional[List]:
    try:
        plan_array = []
        if plan_detail.plan_id is not None:
            res = await get_dashboard_summary_sql(db,current_user.user_id, plan_detail.plan_id )
        else:
            res = await get_dashboard_summary_sql(db,current_user.user_id )
        ret_task_delay = await calculate_task_delay(current_user.user_id, db)
        
        detail_map = {d["plan_id"]: d for d in ret_task_delay} if ret_task_delay else {}
        today = datetime.now(timezone.utc)
        for row in res:
            total_current_tasks = 0
            total_in_progress_tasks = 0
            total_not_started_tasks = 0
            total_delayed_tasks = 0
            total_completed_tasks = 0
            total_completed_tasks_today = 0
            total_objectives = 0
            if isinstance(row["plan_start_date"], datetime):
                time_difference = today - row["plan_start_date"]
                if time_difference.days > 0:
                    start_to_currrent_time_diff = time_difference.days
                else:
                    start_to_currrent_time_diff = 0
            else:
                start_to_currrent_time_diff = 0
            task_delay_row = detail_map.get(row["plan_id"])
            plan_objectives_delay = 0
            if task_delay_row:
                if task_delay_row.get("total_objectives") > 0:
                    plan_objectives_delay = task_delay_row.get("objectives_delayed_time")/task_delay_row.get("total_objectives")
                    total_current_tasks = task_delay_row.get("total_current_tasks")
                    total_in_progress_tasks = task_delay_row.get("total_in_progress_tasks")
                    total_not_started_tasks = task_delay_row.get("total_not_started_tasks")
                    total_delayed_tasks = task_delay_row.get("total_delayed_tasks") 
                    total_completed_tasks = task_delay_row.get("total_completed_tasks")
                    total_completed_tasks_today = task_delay_row.get("total_completed_tasks_today")
                    total_objectives = task_delay_row.get("total_objectives")
            if total_objectives > 0:
                average_task_move = row["task_change_count"]/total_objectives
            else:
                average_task_move = -99999
            
      
            response = {
                "plan": {
                    "plan_id": row["plan_id"],
                    "original_start_date": row["plan_start_date"],
                    "original_end_date": row["plan_end_date"],
                    "task_count": total_objectives,
                    "plan_completion_percent": row["plan_progress"],
                    "completed_tasks": total_completed_tasks,
                    "plan_change_count" : row["plan_change_count"],
                    "task_change_count": row["task_change_count"],
                    "approved_by_user:" : row["approved_by_user"],
                    "plan_goal": row["plan_goal"],
                    "completed_tasks_today" : total_completed_tasks_today,
                    "total_current_tasks" : total_current_tasks,
                    "total_in_progress_tasks": total_in_progress_tasks,
                    "total_not_started_tasks": total_not_started_tasks,
                    "total_delayed_tasks" : total_delayed_tasks
                },
                "goal_discipline_score": calculate_goal_discipline_score(row["plan_id"], 
                                                                         total_objectives,
                                                                         total_completed_tasks,
                                                                         average_task_move, 
                                                                         start_to_currrent_time_diff,
                                                                         plan_objectives_delay,
                                                                        row["plan_change_count"]
                                                                         )
            }
            plan_array.append(response)

        return plan_array
    
    except GeneralDataException as e:

        logger.error(f"Database Error while retrieving the progress datan: {str(e)}")
        raise GeneralDataException(
            "Database Error while retrieving the progress data",
            context={"detail": "Database Error while retrieving the progress data"}
        )
    except TimeZoneException as e:
        logger.error(f"Time manipulation  Error while retrieving the progress data: {str(e)}")
        raise GeneralDataException(
            f"Time manipulation Error while retrieving the progress data: {str(e)}",
            context={"detail": f"Time manipulation Error while retrieving the progress data: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Unexpected Error while retrieving the progress data: {str(e)}")
        raise GeneralDataException(
            "Unexpected Error while retrieving the progress data",
            context={"detail" : "An unexpected Error while retrieving the progress data"}
        )

async def get_plan_dashboard_detail(plan_id, current_user: User, db: AsyncSession):
    try:
        filter_params = {}
        filter_params["plan_id"] = plan_id
        plan = await get_plan(filter_params, db)
        if not plan:
            raise GeneralDataException(
                f"There is no plan with a id {plan_id}",
            context={"detail": f"There is no plan with a id {plan_id}"}
            )
        tasks = await get_executable_plan(filter_params, db)
        entity_progress = await get_progress_tracking_by_plan(db, plan_id, current_user.user_id)
        task_changes = await get_task_change_history(db, plan_id)
        plan_changes = await get_plan_change_history(db, plan_id)

        # Index changes by entity_id
        task_change_map = {}
        for change in task_changes:
            task_change_map.setdefault(change.entity_id, []).append(change)
        task_data = []
        today = datetime.now(timezone.utc)
        for task in tasks:
            change_entries = task_change_map.get(task.entity_id, [])
            print(f"The task plan id and entity id are {task.plan_id}-{task.entity_id}")
            if f"{task.plan_id}-{task.entity_id}" in entity_progress:
                task_progress = entity_progress.get(f"{task.plan_id}-{task.entity_id}").cumulative_progress
                
            else:
                task_progress = 0
                delayed = task.start_date < today and (not task_progress or task_progress.progress_percent < 100)

            task_data.append({
                "entity_id": task.entity_id,
                "start_date": task.start_date,
                "sequence_id": task.sequence_id,
                "move_count": len(change_entries),
                "change_reasons": [c.reason for c in change_entries],
                "status": task_progress,
                "delayed": delayed,
            })

        if f"{plan_id}-{plan_id}" in entity_progress:
            completion_percent = entity_progress.get({f"{plan_id}-{plan_id}"}).cumulative_progress
        else:
            completion_percent = 0
        
        completed_tasks = len([t for t in entity_progress if t["progress_percent"] == 100])
        avg_task_moves = sum(t["move_count"] for t in task_data) / len(task_data) if task_data else 0
        task_delay_penalty = sum(1 for t in task_data if t["delayed"]) / len(task_data) if task_data else 0
        if len(plan_changes) > 0:
            plan_move_count = plan_changes[0].change_count
        else:
            plan_move_count = 0
        
        if isinstance(plan[0].plan_start_date, datetime):
            time_difference = today - plan[0].plan_start_date
            start_to_currrent_time_diff = time_difference.days
        else:
            start_to_currrent_time_diff = -99999


        response = {
            "plan": {
                "plan_id": plan_id,
                "original_start_date": plan[0].plan_start_date,
                "original_end_date": plan[0].plan_end_date,
                "plan_move_count": len(plan_changes),
                "plan_change_reasons": [c.reason for c in plan_changes],
                "plan_completion_percent":  completion_percent
            },
            "tasks": task_data,
            "goal_discipline_score": calculate_goal_discipline_score(plan[0], 
                                                                     len(task_data), 
                                                                     completed_tasks, 
                                                                     avg_task_moves,
                                                                     plan_move_count,
                                                                     task_delay_penalty,
                                                                     start_to_currrent_time_diff
                                                                     )
        }

        return response

    except IntegrityException as e:

        logger.error(f"Integrity Error while retrieving the progress data: {str(e)}")
        raise IntegrityException(
            "Integrity Error while retrieving the progress data",
            context = {"detail": "Error while retrieving the progress data"}
        )
    except GeneralDataException as e:

        logger.error(f"Database Error while retrieving the progress datan: {str(e)}")
        raise GeneralDataException(
            "Database Error while retrieving the progress data",
            context={"detail": "Database Error while retrieving the progress data"}
        )
    except TimeZoneException as e:
        logger.error(f"Time manipulation  Error while retrieving the progress data: {str(e)}")
        raise GeneralDataException(
            f"Time manipulation Error while retrieving the progress data: {str(e)}",
            context={"detail": f"Time manipulation Error while retrieving the progress data: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Unexpected Error while retrieving the progress data: {str(e)}")
        raise GeneralDataException(
            "Unexpected Error while retrieving the progress data",
            context={"detail" : "An unexpected Error while retrieving the progress data"}
        )


async def get_user_dashboard(current_user: User, db: AsyncSession) -> Optional[List]:
    try:
        plan_array = []
        res = await get_dashboard_summary_sql(db,current_user.user_id )
        if res is None or len(res) <= 0:
             response = {
                    "total_plans": 'N/A',
                    "total_active_plans": 'N/A',
                    "total_tasks": 'N/A',
                    "summary_gds": 'N/A',
                    "completed_tasks": 'N/A',
                    "current_tasks": 'N/A',
                    "completed_tasks_for_today": 'N/A'    
                        }
             return response
        ret_task_delay = await calculate_task_delay(current_user.user_id, db)
        
        detail_map = {d["plan_id"]: d for d in ret_task_delay} if ret_task_delay else {}
        today = datetime.now(timezone.utc)
        n_total_plans = 0
        n_total_tasks = 0
        n_gds = 0
        n_completed_tasks = 0
        n_completed_tasks_for_today = 0
        n_total_current_tasks = 0
        n_total_active_plans = 0
        for row in res:
            total_current_tasks = 0
            total_in_progress_tasks = 0
            total_not_started_tasks = 0
            total_delayed_tasks = 0
            total_completed_tasks = 0
            total_completed_tasks_today = 0
            total_objectives = 0

            if isinstance(row["plan_start_date"], datetime):
                time_difference = today - row["plan_start_date"]
                start_to_currrent_time_diff = time_difference.days
            else:
                start_to_currrent_time_diff = 0
            task_delay_row = detail_map.get(row["plan_id"])
            plan_objectives_delay = 0
            if task_delay_row:
                n_total_current_tasks += task_delay_row.get("total_current_tasks")
                if task_delay_row.get("total_objectives") > 0:
                    plan_objectives_delay = task_delay_row.get("objectives_delayed_time")/task_delay_row.get("total_objectives")
                    total_current_tasks = task_delay_row.get("total_current_tasks")
                    total_in_progress_tasks = task_delay_row.get("total_in_progress_tasks")
                    total_not_started_tasks = task_delay_row.get("total_not_started_tasks")
                    total_delayed_tasks = task_delay_row.get("total_delayed_tasks") 
                    total_completed_tasks = task_delay_row.get("total_completed_tasks")
                    total_completed_tasks_today = task_delay_row.get("total_completed_tasks_today")
                    total_objectives = task_delay_row.get("total_objectives")
            if total_objectives > 0:
                average_task_move = row["task_change_count"]/total_objectives
            else:
                average_task_move = -99999
            
            n_total_plans += 1
            n_total_active_plans += row["total_active_plans"]
            n_total_tasks += total_objectives
            n_completed_tasks_for_today += total_completed_tasks_today
            n_completed_tasks += total_completed_tasks
            if row["approved_by_user"] == 99:
                gds = calculate_goal_discipline_score(row["plan_id"], 
                                                                            total_objectives,
                                                                            total_completed_tasks,
                                                                            average_task_move, 
                                                                            start_to_currrent_time_diff,
                                                                            plan_objectives_delay,
                                                                            row["plan_change_count"])
            else:
                gds = "N/A"
            
            if gds != "N/A":                                                        
                n_gds += gds

        response = {
                "total_plans": n_total_plans,
                "total_active_plans": n_total_active_plans,
                "total_tasks": n_total_tasks,
                "summary_gds": n_gds/n_total_plans,
                "completed_tasks": n_completed_tasks,
                "current_tasks": n_total_current_tasks,
                "completed_tasks_for_today": n_completed_tasks_for_today    
                    }

        return response
    
    except GeneralDataException as e:

        logger.error(f"Database Error while retrieving the progress datan: {str(e)}")
        raise GeneralDataException(
            "Database Error while retrieving the progress data",
            context={"detail": "Database Error while retrieving the progress data"}
        )
    except TimeZoneException as e:
        logger.error(f"Time manipulation  Error while retrieving the progress data: {str(e)}")
        raise GeneralDataException(
            f"Time manipulation Error while retrieving the progress data: {str(e)}",
            context={"detail": f"Time manipulation Error while retrieving the progress data: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Unexpected Error while retrieving the progress data: {str(e)}")
        raise GeneralDataException(
            "Unexpected Error while retrieving the progress data",
            context={"detail" : "An unexpected Error while retrieving the progress data"}
        )

