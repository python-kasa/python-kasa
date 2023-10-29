"""Script for testing update performance on devices."""
import asyncio
import time

import asyncclick as click
import pandas as pd

from kasa import Discover


async def _update(dev, lock=None):
    if lock is not None:
        await lock.acquire()
        await asyncio.sleep(2)
    try:
        start_time = time.time()
        # print("%s >> Updating" % id(dev))
        await dev.update()
        # print("%s >> done in %s" % (id(dev), time.time() - start_time))
        return {"id": f"{id(dev)}-{dev.model}", "took": (time.time() - start_time)}
    finally:
        if lock is not None:
            lock.release()


async def _update_concurrently(devs):
    start_time = time.time()
    update_futures = [asyncio.ensure_future(_update(dev)) for dev in devs]
    await asyncio.gather(*update_futures)
    return {"type": "concurrently", "took": (time.time() - start_time)}


async def _update_sequentially(devs):
    start_time = time.time()

    for dev in devs:
        await _update(dev)

    return {"type": "sequential", "took": (time.time() - start_time)}


@click.command()
@click.argument("addrs", nargs=-1)
@click.option("--rounds", default=5)
async def main(addrs, rounds):
    """Test update performance on given devices."""
    print(f"Running {rounds} rounds on {addrs}")
    devs = []

    for addr in addrs:
        try:
            dev = await Discover.discover_single(addr)
            devs.append(dev)
        except Exception as ex:
            print(f"unable to add {addr}: {ex}")

    data = []
    test_gathered = True

    if test_gathered:
        print("=== Testing using gather on all devices ===")
        for _i in range(rounds):
            data.append(await _update_concurrently(devs))
            await asyncio.sleep(2)

        await asyncio.sleep(5)

        for _i in range(rounds):
            data.append(await _update_sequentially(devs))
            await asyncio.sleep(2)

        df = pd.DataFrame(data)
        print(df.groupby("type").describe())

    print("=== Testing per-device performance ===")

    futs = []
    data = []
    locks = {dev: asyncio.Lock() for dev in devs}
    for _i in range(rounds):
        for dev in devs:
            futs.append(asyncio.ensure_future(_update(dev, locks[dev])))

    for fut in asyncio.as_completed(futs):
        res = await fut
        data.append(res)

    df = pd.DataFrame(data)
    print(df.groupby("id").describe())


if __name__ == "__main__":
    main(_anyio_backend="asyncio")
