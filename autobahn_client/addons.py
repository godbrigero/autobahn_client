# TODO

from dataclasses import dataclass
from typing import Awaitable, Callable
from autobahn_client.client import Autobahn

SYSTEM_WORKLOAD_BROADCAST_TOPIC = "autobahn/system/workload/broadcast"

@dataclass
class WorkloadData:
    usage_percentage: float
    is_blocked: bool

class Workload:
    highest_priority_function: Callable[[list["WorkloadData"]], bool]
    
    @classmethod
    def set_highest_priority_function(cls):
        def decorator(
            func: Callable[[list["WorkloadData"]], bool],
        ):
            cls.highest_priority_function = func
            return func
        
        return decorator

    @classmethod
    def get_highest_priority_function(cls):
        return cls.highest_priority_function
    

class WorkloadDistributedPubSub:
    autobahn_instance: Autobahn | None
    distributed_workloads: dict[str, Callable[[bytes], Awaitable[None]]]
    
    @classmethod
    def set_autobahn_instance(cls, autobahn_instance: Autobahn):
        WorkloadDistributedPubSub.autobahn_instance = autobahn_instance
    
    @classmethod
    def distributed_workload_subscription(cls, topic: str):
        def decorator(
            func: Callable[[bytes], Awaitable[None]],
        ):
            cls.distributed_workloads[topic] = func
            return func
        
        return decorator
    
    