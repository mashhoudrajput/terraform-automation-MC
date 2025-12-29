import threading
from typing import Dict, Any
from src.core.database import SessionLocal, ClientStatusEnum
from src.core.client_service import ClientService
from src.core.terraform_service import TerraformService
from src.core.services.db_main import MainHospitalDBService
from src.core.services.db_sub import SubHospitalDBService
from src.api.error_handler import enhance_terraform_error


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
