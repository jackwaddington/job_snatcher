"""
Wake-on-LAN utility for waking the gaming PC before running inference.
"""
import logging
import socket
import struct
import time

import requests

logger = logging.getLogger(__name__)


def send_magic_packet(mac_address: str) -> None:
    """Send a WoL magic packet to the given MAC address."""
    mac = mac_address.replace(':', '').replace('-', '')
    if len(mac) != 12:
        raise ValueError(f"Invalid MAC address: {mac_address}")

    raw = bytes.fromhex(mac)
    packet = b'\xff' * 6 + raw * 16

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, ('<broadcast>', 9))

    logger.info(f"Magic packet sent to {mac_address}")


def is_reachable(host: str, port: int = 11434, timeout: int = 3) -> bool:
    """Check if the gaming PC's Ollama endpoint is reachable."""
    try:
        requests.get(f"http://{host}:{port}", timeout=timeout)
        return True
    except Exception:
        return False


def wake_and_wait(mac_address: str, ollama_host: str, ollama_port: int = 11434,
                  retries: int = 3, boot_wait: int = 30) -> bool:
    """
    Send WoL packet and wait for the gaming PC to come online.
    Returns True if online, False if failed after retries.
    """
    from src.metrics import wol_success, wol_failure

    if is_reachable(ollama_host, ollama_port):
        logger.info("Gaming PC already online.")
        return True

    for attempt in range(1, retries + 1):
        logger.info(f"WoL attempt {attempt}/{retries}...")
        try:
            send_magic_packet(mac_address)
        except Exception as e:
            logger.warning(f"Failed to send magic packet: {e}")

        logger.info(f"Waiting {boot_wait}s for boot...")
        time.sleep(boot_wait)

        if is_reachable(ollama_host, ollama_port):
            wol_success.inc()
            logger.info("Gaming PC is online.")
            return True

    wol_failure.inc()
    logger.error("Gaming PC did not come online after all retries.")
    return False
