import threading
import time
import random

class BaseAgent(threading.Thread):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.role = "Unassigned"
        self.objective = "Awaiting orders"
        self._stop_event = threading.Event()
        self.system_prompt = "Initial baseline instructions."
        self.performance_score = 100

    def set_mission(self, role, objective):
        """Dynamic assignment of role and objective."""
        self.role = role
        self.objective = objective
        self.system_prompt = f"Act as a {role}. Your main goal is: {objective}."
        print(f"[{self.name}] Mission updated. Role: {self.role} | Objective: {self.objective}")

    def stop(self):
        """Triggers the kill switch for this agent."""
        print(f"[{self.name}] Kill switch activated! Attempting graceful shutdown...")
        self._stop_event.set()

    def reflect_and_improve(self, error_reason):
        """Self-improvement loop to adjust internal logic after failure."""
        print(f"[{self.name}] REFLECTING on failure: '{error_reason}'")
        time.sleep(1) # Simulating thinking
        self.system_prompt += f"\n- Avoided Error: Do not do {error_reason} again."
        print(f"[{self.name}] SYSTEM PROMPT UPDATED. Self-improvement applied.")

    def run(self):
        """Main execution loop. Constantly checks the kill switch."""
        print(f"[{self.name}] Agent started. Executing mission...")
        
        iteration = 0
        while not self._stop_event.is_set():
            # Simulating agent work
            print(f"[{self.name}] Processing step {iteration}...")
            
            # Simulate a random failure to trigger self-improvement
            if random.random() < 0.1: # 10% chance to fail
                print(f"[{self.name}] ERROR encountered during processing!")
                self.reflect_and_improve(f"Mistake made at step {iteration}")
                
            time.sleep(2) # Simulating time taken for an LLM response or task
            iteration += 1

        print(f"[{self.name}] SHUTDOWN COMPLETE. Agent terminated safely.")
