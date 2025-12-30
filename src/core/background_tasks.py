import threading
import logging
from typing import Dict, Any
from src.core.database import SessionLocal, ClientStatusEnum
from src.core.client_service import ClientService
from src.core.terraform_service import TerraformService
from src.core.services.db_main import MainHospitalDBService
from src.core.services.db_sub import SubHospitalDBService
from src.api.error_handler import enhance_terraform_error

logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._tasks = {}
                    cls._instance._threads = {}
        return cls._instance
    
    def deploy_hospital(self, client_uuid: str, client_info: Dict[str, Any]):
        def task():
            db = SessionLocal()
            try:
                client_service = ClientService()
                terraform_service = TerraformService()
                db_service = MainHospitalDBService()
                
                client_service.update_client_status(db, client_uuid, ClientStatusEnum.IN_PROGRESS)
                
                success, outputs, error_message = terraform_service.run_full_deployment(client_uuid, client_info)
                
                if success:
                    client_service.update_client_outputs(db, client_uuid, outputs)
                    client_service.update_client_status(db, client_uuid, ClientStatusEnum.COMPLETED)
                    
                    # Auto-create tables for main hospital
                    try:
                        region = client_info.get('region')
                        terraform_outputs = client_service.parse_terraform_outputs(outputs)
                        private_bucket_name = terraform_outputs.private_bucket_name if terraform_outputs else None
                        
                        if private_bucket_name:
                            logger.info(f"Auto-creating tables for hospital {client_uuid}...")
                            table_success, table_message = db_service.create_tables(client_uuid, region, private_bucket_name)
                            if table_success:
                                logger.info(f"Tables created successfully for hospital {client_uuid}")
                            else:
                                logger.warning(f"Failed to auto-create tables for hospital {client_uuid}: {table_message}")
                        else:
                            logger.warning(f"Private bucket name not found in outputs for hospital {client_uuid}")
                    except Exception as table_error:
                        logger.error(f"Error during auto table creation for hospital {client_uuid}: {str(table_error)}")
                else:
                    enhanced_error = enhance_terraform_error(error_message)
                    client_service.update_client_status(db, client_uuid, ClientStatusEnum.FAILED, enhanced_error)
            except Exception as e:
                try:
                    client_service = ClientService()
                    client_service.update_client_status(db, client_uuid, ClientStatusEnum.FAILED, str(e))
                except:
                    pass
            finally:
                db.close()
                with self._lock:
                    if client_uuid in self._threads:
                        del self._threads[client_uuid]
                    if client_uuid in self._tasks:
                        del self._tasks[client_uuid]
        
        thread = threading.Thread(target=task, daemon=True)
        thread.start()
        
        with self._lock:
            self._tasks[client_uuid] = task
            self._threads[client_uuid] = thread
    
    def deploy_sub_hospital(self, client_uuid: str, parent_uuid: str, client_info: Dict[str, Any]):
        def task():
            db = SessionLocal()
            try:
                client_service = ClientService()
                terraform_service = TerraformService()
                
                client_service.update_client_status(db, client_uuid, ClientStatusEnum.IN_PROGRESS)
                
                parent_hospital = client_service.get_client_by_uuid(db, parent_uuid)
                if not parent_hospital:
                    client_service.update_client_status(db, client_uuid, ClientStatusEnum.FAILED, "Parent hospital not found")
                    return
                
                if parent_hospital.status != ClientStatusEnum.COMPLETED:
                    client_service.update_client_status(
                        db, client_uuid, ClientStatusEnum.FAILED,
                        "Parent hospital deployment not completed"
                    )
                    return
                
                success, outputs, error_message = terraform_service.run_full_deployment(client_uuid, client_info)
                
                if success:
                    client_service.update_client_outputs(db, client_uuid, outputs)
                    client_service.update_client_status(db, client_uuid, ClientStatusEnum.COMPLETED)
                    
                    # Auto-create tables for sub-hospital
                    try:
                        from src.core.services.db_sub import SubHospitalDBService
                        
                        region = client_info.get('region')
                        terraform_outputs = client_service.parse_terraform_outputs(outputs)
                        private_bucket_name = terraform_outputs.private_bucket_name if terraform_outputs else None
                        database_name = terraform_outputs.database_name if terraform_outputs else None
                        
                        if private_bucket_name and database_name:
                            logger.info(f"Auto-creating tables for sub-hospital {client_uuid}...")
                            sub_db_service = SubHospitalDBService()
                            table_success, table_message = sub_db_service.create_tables(
                                client_uuid, parent_uuid, database_name, region, private_bucket_name
                            )
                            if table_success:
                                logger.info(f"Tables created successfully for sub-hospital {client_uuid}")
                            else:
                                logger.warning(f"Failed to auto-create tables for sub-hospital {client_uuid}: {table_message}")
                        else:
                            missing = []
                            if not private_bucket_name:
                                missing.append("private_bucket_name")
                            if not database_name:
                                missing.append("database_name")
                            logger.warning(f"Missing required outputs for sub-hospital {client_uuid}: {', '.join(missing)}")
                    except Exception as table_error:
                        logger.error(f"Error during auto table creation for sub-hospital {client_uuid}: {str(table_error)}")
                else:
                    enhanced_error = enhance_terraform_error(error_message)
                    client_service.update_client_status(db, client_uuid, ClientStatusEnum.FAILED, enhanced_error)
            except Exception as e:
                try:
                    client_service = ClientService()
                    client_service.update_client_status(db, client_uuid, ClientStatusEnum.FAILED, str(e))
                except:
                    pass
            finally:
                db.close()
                with self._lock:
                    if client_uuid in self._threads:
                        del self._threads[client_uuid]
                    if client_uuid in self._tasks:
                        del self._tasks[client_uuid]
        
        thread = threading.Thread(target=task, daemon=True)
        thread.start()
        
        with self._lock:
            self._tasks[client_uuid] = task
            self._threads[client_uuid] = thread
    
    def is_running(self, client_uuid: str) -> bool:
        with self._lock:
            return client_uuid in self._threads and self._threads[client_uuid].is_alive()


task_manager = BackgroundTaskManager()
