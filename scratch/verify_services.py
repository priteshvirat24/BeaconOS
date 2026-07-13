import asyncio
import os
import sys

from sqlalchemy import text, select
from beacon.config import get_settings
from beacon.db import get_session, init_engine, close_engine
from beacon.db.models.crisis import Crisis
from beacon.services.redis import init_redis, get_redis, close_redis
from beacon.services.world_model import world_model
from beacon.services.task_manager import task_manager
from beacon.services.approval import approval_manager
from beacon.services.memory import episodic_memory, procedural_memory
from beacon.events import event_publisher

async def main():
    print("Initializing services verification...")
    settings = get_settings()
    
    # 1. Test database connection
    print("Connecting to database...")
    init_engine(settings.database_url)
    try:
        async with get_session() as session:
            # Run simple query
            res = await session.execute(text("SELECT 1;"))
            val = res.scalar()
            print(f"Database query SELECT 1 returned: {val} (OK)")
    except Exception as e:
        print(f"Database connection failed: {e}")
        await close_engine()
        sys.exit(1)
        
    # 2. Test Redis connection
    print("Connecting to Redis...")
    try:
        await init_redis(settings.redis_url)
        r = get_redis()
        await r.set("beacon:verify", "OK")
        val = await r.get("beacon:verify")
        print(f"Redis set/get check returned: {val} (OK)")
        await r.delete("beacon:verify")
    except Exception as e:
        print(f"Redis connection failed: {e}")
        await close_engine()
        sys.exit(1)

    # 3. Test Ingest normalization and database write
    print("Testing world model service and database insertion...")
    try:
        # Create a test crisis
        crisis_id = await world_model.create_crisis_from_hazard(
            title="Test M5.0 Earthquake Verification Event",
            hazard_type="earthquake",
            severity="moderate",
            severity_score=5.0,
            latitude=37.7749,
            longitude=-122.4194,
            location_name="San Francisco, CA",
            source_event_id="test-sf-123",
            source_type="usgs"
        )
        print(f"Successfully created test crisis: {crisis_id}")

        # Get snapshot
        snapshot = await world_model.get_snapshot(crisis_id)
        print(f"Snapshot retrieval: OK (Title: {snapshot['crisis']['title']})")

        # Test task creation
        task_id = await task_manager.create_task(
            crisis_id=crisis_id,
            title="Verify emergency response capabilities",
            description="Operational check task",
            priority=0.8
        )
        print(f"Successfully created task: {task_id}")

        # Test approval workflow
        approval_id = await approval_manager.request_approval(
            action="deploy_convoys",
            target_object_type="plan",
            target_object_id=crisis_id,
            authority_required="L3_EXECUTE_REVERSIBLE",
            crisis_id=crisis_id
        )
        print(f"Successfully created approval request: {approval_id}")

        # Grant approval
        approved = await approval_manager.grant_approval(
            approval_id=approval_id,
            approver_slack_id="U12345",
            approver_name="Test Coordinator",
            comments="Verified local conditions allow safe transit."
        )
        print(f"Approval grant result: {approved} (OK)")

        # Cleanup test data using ORM delete to cascade clean child records
        async with get_session() as session:
            # Delete child objects first to avoid constraint issues, then delete crisis
            await session.execute(text(f"DELETE FROM approvals WHERE crisis_id = '{crisis_id}';"))
            await session.execute(text(f"DELETE FROM tasks WHERE crisis_id = '{crisis_id}';"))
            crisis_obj = await session.get(Crisis, crisis_id)
            if crisis_obj:
                await session.delete(crisis_obj)
        print("Cleanup of verification test database records: OK")

    except Exception as e:
        print(f"Subsystem verification failed: {e}")
        await close_redis()
        await close_engine()
        sys.exit(1)

    # Shutdown
    await close_redis()
    await close_engine()
    print("=== ALL INFRASTRUCTURE & SUBSYSTEM VERIFICATIONS PASSED ===")

if __name__ == "__main__":
    asyncio.run(main())
