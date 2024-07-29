#!/home/urjaman/.local/share/pipx/venvs/glasgow/bin/python

import asyncio
import logging
import argparse

from glasgow.applet import GlasgowAppletError, GlasgowApplet
from glasgow.applet.interface.uart import UARTApplet
from glasgow.applet.interface.spi_flashrom import SPIFlashromApplet
from glasgow.target.hardware import GlasgowHardwareTarget
from glasgow.device.hardware import GlasgowHardwareDevice
from glasgow.access.direct import DirectMultiplexer, DirectDemultiplexer, DirectArguments

logger = logging.getLogger(__loader__.name)

def pinargs(x):
    r = []
    for k in x.keys():
        r.append(f"--pin-{k}")
        r.append(str(x[k]))
    return r

async def _main():
    device = GlasgowHardwareDevice()
    await device.reset_alert("AB")
    await device.poll_alert()
    await device.set_voltage("AB", 3.3)
    target = GlasgowHardwareTarget(revision=device.revision,
                                    multiplexer_cls=DirectMultiplexer,
                                    with_analyzer=False)
    access_args = DirectArguments(applet_name="uart-frser",
                                    default_port="AB",
                                    pin_count=16)
    uart_parser = argparse.ArgumentParser('uart')
    spifr_parser = argparse.ArgumentParser('spi-flashrom')
    UARTApplet.add_build_arguments(uart_parser, access_args)
    SPIFlashromApplet.add_build_arguments(spifr_parser, access_args)
    UARTApplet.add_run_arguments(uart_parser, access_args)
    SPIFlashromApplet.add_run_arguments(spifr_parser, access_args)
    UARTApplet.add_interact_arguments(uart_parser)
    SPIFlashromApplet.add_interact_arguments(spifr_parser)
    volts = ["-V", "2.7"]

    uart_pins = {
        "rx": 4,
        "tx": 5
    }
    spi_pins = {
        "cs": 0,
        "cipo": 1,
        "sck":  2,
        "copi": 3,
        "wp": 6,
        "hold": 7
    }

    uart_args = uart_parser.parse_args(volts + pinargs(uart_pins) + [ "-b", "115200", "tty"])
    spifr_args = spifr_parser.parse_args(volts + pinargs(spi_pins) + [ "--freq", "4000", "tcp::2222"])

    uart = UARTApplet()
    spifr = SPIFlashromApplet()
    uart.build(target, uart_args)
    spifr.build(target, spifr_args)
    plan = target.build_plan()
    await device.download_target(plan)
    device.demultiplexer = DirectDemultiplexer(device, target.multiplexer.pipe_count)

    async def run_applet(applet: GlasgowApplet, args):
        try:
            iface = await applet.run(device, args)
            return await applet.interact(device, args, iface)
        except GlasgowAppletError as e:
            applet.logger.error(str(e))
            return 1
        except asyncio.CancelledError:
            return 130 # 128 + SIGINT
        finally:
            await device.demultiplexer.flush()
            device.demultiplexer.statistics()

    tasks = [
        asyncio.ensure_future(run_applet(uart, uart_args)),
        asyncio.ensure_future(run_applet(spifr, spifr_args))
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)

def main():
    root_logger = logging.getLogger()
    term_handler = logging.StreamHandler()
    root_logger.addHandler(term_handler)

    exit(asyncio.new_event_loop().run_until_complete(_main()))


if __name__ == "__main__":
    main()
