import subprocess


def discover_hosts(networks: list[str], timeout: int = 10) -> list[str]:
    """
    Perform a ping sweep to discover live hosts on the given networks.

    Args:
        networks: List of network ranges in CIDR notation (e.g., ["192.168.1.0/24"])
        timeout: Host timeout in seconds (passed to nmap)

    Returns:
        List of discovered host IPs

    Raises:
        RuntimeError: If the nmap command fails
    """
    network_args = " ".join(networks)
    cmd = f"nmap -n -sn -T5 -PE -PP -PM -PR --host-timeout {timeout}s {network_args} | grep '^Nmap scan' | awk '{{print $5}}'"

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0 and result.stderr:
        raise RuntimeError(f"nmap failed: {result.stderr}")

    if not result.stdout:
        return []

    return result.stdout.strip().splitlines()


def scan_ports(hosts: list[str], timeout: int = 30) -> dict[str, list[str]]:
    """
    Perform a fast port scan on the given hosts.

    Args:
        hosts: List of host IPs to scan
        timeout: Host timeout in seconds (passed to nmap, per host)

    Returns:
        Dict mapping each host to a list of open ports (e.g., {"192.168.1.1": ["22/tcp", "80/tcp"]})

    Raises:
        RuntimeError: If the nmap command fails
    """
    results = {}

    for host in hosts:
        cmd = f"nmap -n -F -T5 --host-timeout {timeout}s {host}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if result.returncode != 0 and result.stderr:
            raise RuntimeError(f"nmap failed for {host}: {result.stderr}")

        open_ports = []
        for line in result.stdout.splitlines():
            if "/tcp" in line and "open" in line:
                port = line.split()[0]
                open_ports.append(port)

        results[host] = open_ports

    return results