import platform
import subprocess
import time
import shutil
from random import choice
from src.logging import logger
class ExpressVPN:
    VPN_LOCATIONS = [
        "usa", "uk", "germany", "spain", "france",
        "netherlands", "canada", "australia", "singapore",
    ]

    def __init__(self):
        self.system = platform.system()
        if self.system == "Windows":
            self.cli = self.find_windows_cli()

        elif self.system == "Linux":
            self.cli = self.find_linux_cli()

        else:
            raise RuntimeError(
                f"Unsupported operating system: {self.system}"
            )

        print("Operating System:", self.system)
        print("ExpressVPN CLI:", self.cli)
        
    def find_windows_cli(self):

        possible_paths = [
            r"C:\Program Files (x86)\ExpressVPN\services\expressvpnctl.exe",
            r"C:\Program Files\ExpressVPN\expressvpnctl.exe",
            r"C:\Program Files\ExpressVPN\services\expressvpnctl.exe",
        ]

        for path in possible_paths:
            if shutil.os.path.exists(path):
                return path

        # Check PATH
        cli = shutil.which("expressvpnctl")

        if cli:
            return cli

        raise FileNotFoundError(
            "expressvpnctl.exe was not found on Windows."
        )

    def find_linux_cli(self):

        possible_paths = [
            "/usr/local/bin/expressvpnctl",
            "/opt/expressvpn/bin/expressvpnctl",
        ]

        for path in possible_paths:
            if shutil.os.path.exists(path):
                return path

        cli = shutil.which("expressvpnctl")

        if cli:
            return cli

        raise FileNotFoundError(
            "expressvpnctl was not found on Linux."
        )

    # def get_vpn_locations(self):
    #     result = subprocess.run(
    #         ["expressvpnctl", "get", "regions"],
    #         capture_output=True,
    #         text=True,
    #         check=True
    #     )

    #     locations = []

    #     for line in result.stdout.splitlines():

    #         line = line.strip()

    #         if line.contains(["usa","UK","Germany","Spain","France","Netherland","Canada only","Australia","Singapore"]):
    #             locations.append(line)

    #     return locations
    
    def get_vpn_locations(self):
        try:
            result = subprocess.run(
                ["expressvpnctl", "get", "regions"],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"expressvpnctl failed: {e.stderr}")
            return []
        except FileNotFoundError:
            print("expressvpnctl not found on PATH")
            return []

        locations = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            lower = line.lower()
            if any(name in lower for name in self.VPN_LOCATIONS):
                locations.append(line)

        return locations
    
    def run(self, *args):

        command = [self.cli, *args]

        print("Running:", " ".join(command))

        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

        if result.stdout:
            print(result.stdout)

        if result.stderr:
            print(result.stderr)

        if result.returncode != 0:
            raise RuntimeError(
                f"ExpressVPN command failed: {command}"
            )

        return result.stdout

    def connect(self, location="smart"):

        if self.system == "Linux":

            self.run("background", "enable")

        logger.info(f"Using {location}")

        self.run("connect", location)

        time.sleep(5)

        return self.status()

    def disconnect(self):

        return self.run("disconnect")

    def status(self):

        return self.run("status")

    def locations(self):

        return self.run("get", "regions")


if __name__ == "__main__":

    vpn = ExpressVPN()
    locations = vpn.get_vpn_locations()
    # print(locations)
    # According to the logic if we have to check if the same location can be connected again or not. If the process is done then we can connect to the same location again. If not then we have to disconnect and then connect to the same location again.
    vpn.connect(choice(locations))
    
    vpn.disconnect()