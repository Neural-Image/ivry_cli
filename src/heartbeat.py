import threading
import time
import requests
from typing import Optional
import logging

logger = logging.getLogger("heartbeat")

class HeartbeatManager:
    """管理与服务器的心跳机制"""
    
    def __init__(self, upload_url: str, model_id: str, api_key: str, interval: int = 3600):
        """
        初始化心跳管理器
        
        Args:
            upload_url: 心跳上传的URL
            model_id: 模型ID
            api_key: API密钥
            interval: 心跳间隔(秒)，默认3600秒(1小时)
        """
        self.upload_url = upload_url
        self.model_id = model_id
        self.api_key = api_key
        self.interval = interval
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_heartbeat_time = 0
        self.last_heartbeat_status = False
    
    def start(self):
        """启动心跳线程"""
        if self.running:
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.thread.start()
        logger.info(f"Heartbeat manager started with interval of {self.interval} seconds")
    
    def stop(self):
        """停止心跳线程"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
            self.thread = None
        logger.info("Heartbeat manager stopped")
    
    def _heartbeat_loop(self):
        """心跳循环"""
        while self.running:
            try:
                self._send_heartbeat()
                # 睡眠到下次心跳时间，但每1秒检查一次是否应该停止
                for _ in range(self.interval):
                    if not self.running:
                        break
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {str(e)}")
                # 发生错误后等待较短时间再重试
                time.sleep(60)
    
    def _send_heartbeat(self):
        """发送单次心跳"""
        try:
            payload = {
                "model_id": self.model_id,
                "timestamp": int(time.time()),
                "status": "active"
            }
            
            headers = {
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                f"{self.upload_url}/heartbeat",
                json=payload,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                self.last_heartbeat_time = time.time()
                self.last_heartbeat_status = True
                logger.debug(f"Heartbeat sent successfully: {response.json()}")
                return True
            else:
                self.last_heartbeat_status = False
                logger.warning(f"Failed to send heartbeat. Status code: {response.status_code}, Response: {response.text}")
                return False
                
        except requests.RequestException as e:
            self.last_heartbeat_status = False
            logger.error(f"Network error when sending heartbeat: {str(e)}")
            return False
        except Exception as e:
            self.last_heartbeat_status = False
            logger.error(f"Unexpected error when sending heartbeat: {str(e)}")
            return False
            
    def get_status(self):
        """获取心跳状态"""
        return {
            "running": self.running,
            "last_heartbeat_time": self.last_heartbeat_time,
            "last_heartbeat_status": self.last_heartbeat_status,
            "seconds_since_last_heartbeat": int(time.time() - self.last_heartbeat_time) if self.last_heartbeat_time else None
        }