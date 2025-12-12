import logging
import structlog
import os

def configure_logging():
    '''
    log_directory = "logs"
    os.makedirs(log_directory, exist_ok=True)
    log_file_path = os.path.join(log_directory, "app.log")
    '''

    '''
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[
            #logging.FileHandler(log_file_path),
            logging.StreamHandler(),
        ],
    )
    '''
    
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,  # For request-scoped vars
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()  # Pretty for dev, use JSONRenderer for prod
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )
