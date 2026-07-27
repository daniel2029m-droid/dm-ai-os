import time
from orchestrator import Orchestrator

def main():
    manager = Orchestrator()
    
    print("--- 1. Testing Dynamic Objective Assignment ---")
    a1 = manager.spawn_agent("Agent-Omega", "System Optimizer", "Find redundant files and free up disk space")
    
    print("\n--- 2. Starting Agent ---")
    manager.start_all()
    
    print("\n--- 3. Letting Agent run and potentially self-improve (5 seconds) ---")
    time.sleep(5)
    
    print("\n--- 4. Testing Kill Switch ---")
    manager.global_kill_switch()
    
if __name__ == "__main__":
    main()
