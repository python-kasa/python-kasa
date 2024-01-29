"""Parse pcaps for TP-Link communications."""

import json
from collections import Counter, defaultdict
from pprint import pformat as pf

import click
import dpkt
from dpkt.ethernet import ETH_TYPE_IP, Ethernet

from kasa.cli import echo
from kasa.xortransport import XorEncryption


def read_payloads_from_file(file):
    """Read the given pcap file and yield json payloads."""
    pcap = dpkt.pcap.Reader(file)
    for _ts, pkt in pcap:
        eth = Ethernet(pkt)
        if eth.type != ETH_TYPE_IP:
            continue

        ip = eth.ip
        if ip.p == 6:
            transport = ip.tcp
        elif ip == 17:
            transport = ip.udp
        else:
            continue

        if transport.sport != 9999 and transport.dport != 9999:
            continue

        data = transport.data

        try:
            decrypted = XorEncryption.decrypt(data[4:])
        except Exception as ex:
            echo(f"[red]Unable to decrypt the data, ignoring: {ex}[/red]")
            continue

        if not decrypted:  # skip empty payloads
            continue

        try:
            json_payload = json.loads(decrypted)
        except Exception as ex:
            # this can happen when the response is split into multiple tcp segments
            echo(f"[red]Unable to parse payload '{decrypted}', ignoring: {ex}[/red]")
            continue

        if not json_payload:  # ignore empty payloads
            echo("[red]Got empty payload, ignoring[/red]")
            continue

        yield json_payload


@click.command()
@click.argument("file", type=click.File("rb"))
def parse_pcap(file):
    """Parse pcap file and pretty print the communications and some statistics."""
    seen_items = defaultdict(Counter)

    for json_payload in read_payloads_from_file(file):
        context = json_payload.pop("context", "")
        for module, cmds in json_payload.items():
            seen_items["modules"][module] += 1
            if "err_code" in cmds:
                echo("[red]Got error for module: %s[/red]" % cmds)
                continue

            for cmd, response in cmds.items():
                seen_items["commands"][cmd] += 1
                seen_items["full_command"][f"{module}.{cmd}"] += 1
                if response is None:
                    continue
                direction = ">>"
                if response is None:
                    echo(f"got none as response for {cmd} %s, weird?")
                    continue
                is_success = "[green]+[/green]"
                if "err_code" in response:
                    direction = "<<"
                    if response["err_code"] != 0:
                        seen_items["errorcodes"][response["err_code"]] += 1
                        seen_items["errors"][response["err_msg"]] += 1
                        is_success = "[red]![/red]"

                context_str = f" [ctx: {context}]" if context else ""

                echo(
                    f"[{is_success}] {direction}{context_str} {module}.{cmd}:"
                    f" {pf(response)}"
                )

    echo(pf(seen_items))


if __name__ == "__main__":
    parse_pcap()
