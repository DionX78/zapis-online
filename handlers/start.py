from handlers.booking import welcome


async def cmd_start(uid, platform="max"):
    await welcome(uid, platform=platform)