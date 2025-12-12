# Update your exception.py file:

from typing import Any, Dict

class DataLayerException(Exception):
    """Base exception for data layer errors"""
    def __init__(self, message: str, context: Dict[str, Any] = None):
        self.message = message
        self.context = context or {}
        super().__init__(self.message)

class RecordNotFoundException(DataLayerException):
    """Specific exception for when a record is not found"""
    pass

class DatabaseConnectionException(DataLayerException):
    """Exception for database connection issues"""
    pass

class IntegrityException(DataLayerException):
    """Exception for database connection issues"""
    pass

class MissingDataException(DataLayerException):
    """Exception for database connection issues"""
    pass

class GeneralDataException(DataLayerException):
    """Exception for database connection issues"""
    pass

class TimeZoneException(DataLayerException):
    pass

# Business Logic Base Exception - inherits from BaseException
class BusinessLogicException(BaseException):
    """Base class for business logic exceptions that should bypass generic Exception handlers"""
    def __init__(self, reason: str, **kwargs):
        self.reason = reason
        for key, value in kwargs.items():
            setattr(self, key, value)
        super().__init__(reason)

class UserNotFound(Exception): 
    def __init__(self, user_id: str, reason: str = "User not found"):
        self.user_id = user_id
        self.reason = reason

class PlanExists(Exception): 
    def __init__(self, plan_id: str, reason: str = "The plan you are trying to create exist already"):
        self.plan_id = plan_id
        self.reason = reason



class PlanAlreadyApproved(Exception): 
    def __init__(self, plan_id: str, reason: str = "The Plan you are trying to approve has already been approved"):
        self.plan_id = plan_id
        self.reason = reason

# UPDATED: These now inherit from BusinessLogicException (BaseException)
class PlanContextChange(BusinessLogicException): 
    def __init__(self, prompt_text: str, reason: str = "The plan context has changed"):
        self.prompt_text = prompt_text
        super().__init__(reason, prompt_text=prompt_text)

class PlanIllegalText(BusinessLogicException): 
    def __init__(self, prompt_text: str, reason: str = "Illegal or text not allowed"):
        self.prompt_text = prompt_text
        super().__init__(reason, prompt_text=prompt_text)

class NotEnoughInfoToGenerateGoal(BusinessLogicException): 
    def __init__(self, prompt_text: str, reason: str = "We don't have enough information to generate goal. Please add more context"):
        self.prompt_text = prompt_text
        super().__init__(reason, prompt_text=prompt_text)

class YoudraOpenAIError(Exception): 
    def __init__(self, prompt_text: str, reason: str = "User not found"):
        self.prompt_text = prompt_text
        self.reason = reason

class YoudraGeminiError(Exception): 
    def __init__(self, prompt_text: str, reason: str = "User not found"):
        self.prompt_text = prompt_text
        self.reason = reason