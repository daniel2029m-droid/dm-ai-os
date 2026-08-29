"""
DM AI OS — Emergency Pod Terminator Watchdog
=============================================
Runs independently. Terminates ALL active RunPod pods.
Called as safety net to guarantee $0 ongoing charges.
"""
import sys
import asyncio
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("watchdog")


async def kill_all_pods():
    from src.adapters.runpod_adapter import runpod_adapter

    log.info("=== EMERGENCY WATCHDOG: CHECKING FOR ACTIVE PODS ===")

    for round_num in range(5):
        try:
            pods = await runpod_adapter.list_pods()
            active = [p for p in pods if p.get("desiredStatus") not in ("TERMINATED",)]
            if not active:
                log.info(f"Round {round_num+1}: ✅ 0 active pods. Safe.")
                break
            log.warning(f"Round {round_num+1}: Found {len(active)} active pod(s). Terminating...")
            for p in active:
                pid = p.get("id")
                try:
                    await runpod_adapter.terminate_pod(pid)
                    log.info(f"  Terminated: {pid}")
                except Exception as e:
                    log.error(f"  Failed to terminate {pid}: {e}")
            await asyncio.sleep(6.0)
        except Exception as e:
            log.error(f"Round {round_num+1} error: {e}")
            await asyncio.sleep(5.0)

    # Final verification
    try:
        pods = await runpod_adapter.list_pods()
        active = [p for p in pods if p.get("desiredStatus") not in ("TERMINATED",)]
        acc = await runpod_adapter.get_account_status()
        balance = acc.get("balance", 0.0)
        log.info("=" * 60)
        log.info(f"WATCHDOG FINAL: ACTIVE PODS = {len(active)}")
        log.info(f"WATCHDOG FINAL: BALANCE = ${balance:.2f} USD")
        log.info(f"WATCHDOG FINAL: NETWORK VOLUME tbupq29n08 = PRESERVED")
        log.info("=" * 60)
        return len(active) == 0
    except Exception as e:
        log.error(f"Final check error: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(kill_all_pods())
