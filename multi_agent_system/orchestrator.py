import time
import threading
from agent_core import BaseAgent

class Orchestrator:
    def __init__(self):
        self.agents = []

    def spawn_agent(self, name, role, objective):
        """Creates and assigns a mission to a new agent."""
        agent = BaseAgent(name)
        agent.set_mission(role, objective)
        self.agents.append(agent)
        return agent

    def start_all(self):
        """Starts the execution thread for all registered agents."""
        print("[Orchestrator] Starting all agents...")
        for agent in self.agents:
            agent.start()

    def global_kill_switch(self):
        """Panic button: Stops all running agents immediately."""
        print("\n[!!!] GLOBAL KILL SWITCH TRIGGERED [!!!]")
        for agent in self.agents:
            agent.stop()
            
        print("[Orchestrator] Waiting for agents to terminate...")
        for agent in self.agents:
            agent.join() # Wait for the thread to fully close
        print("[Orchestrator] All agents successfully terminated. System safe.")

if __name__ == "__main__":
    # Test execution
    manager = Orchestrator()
    a1 = manager.spawn_agent("Agent-Security", "Security Auditor", "Scan ports for vulnerabilities")
    a2 = manager.spawn_agent("Agent-Analyzer", "Data Analyst", "Process system logs")
    
    manager.start_all()
    
    try:
        # Keep main thread alive to watch agents work
        print("\n[System] Press Ctrl+C at any time to trigger the GLOBAL KILL SWITCH.\n")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # Catch Ctrl+C to trigger the kill switch gracefully
        manager.global_kill_switch()
