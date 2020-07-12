"""Parse pcaps for TP-Link communications."""

import json
from collections import Counter, defaultdict
from pprint import pformat as pf
from pprint import pprint as pp

import click
import dpkt
from dpkt.ethernet import ETH_TYPE_IP, Ethernet
from kasa.protocol import TPLinkSmartHomeProtocol


def read_payloads_from_file(file):
    """Read the given pcap file and yield json payloads."""
    pcap = dpkt.pcap.Reader(file)
    for ts, pkt in pcap:
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
            decrypted = TPLinkSmartHomeProtocol.decrypt(data[4:])
        except Exception as ex:
            click.echo(
                click.style(f"Unable to decrypt the data, ignoring: {ex}", fg="red")
            )
            continue

        try:
            json_payload = json.loads(decrypted)
        except Exception as ex:
            click.echo(
                click.style(f"Unable to parse payload, ignoring: {ex}", fg="red")
            )
            continue

        if not json_payload:  # ignore empty payloads
            click.echo(click.style("Got empty payload, ignoring", fg="red"))
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
                click.echo(click.style("Got error for module: %s" % cmds, fg="red"))
                continue

            for cmd, response in cmds.items():
                seen_items["commands"][cmd] += 1
                seen_items["full_command"][f"{module}.{cmd}"] += 1
                if response is None:
                    continue
                direction = ">>"
                style = {}
                if response is None:
                    print("got none as response for %s, weird?" % (cmd))
                    continue
                if "err_code" in response:
                    direction = "<<"
                    if response["err_code"] != 0:
                        seen_items["errorcodes"][response["err_code"]] += 1
                        seen_items["errors"][response["err_msg"]] += 1
                        print(response)
                        style = {"bold": True, "fg": "red"}
                    else:
                        style = {"fg": "green"}

                context_str = f" [ctx: {context}]" if context else ""

                click.echo(
                    click.style(
                        f"{direction}{context_str} {module}.{cmd}: {pf(response)}",
                        **style,
                    )
                )

    pp(seen_items)


if __name__ == "__main__":
    parse_pcap()
