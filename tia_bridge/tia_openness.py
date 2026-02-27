"""
TIA Portal Openness API Wrapper
================================
Python wrapper around Siemens.Engineering.dll using pythonnet.
This file runs on WINDOWS only (where TIA Portal is installed).

Requires:
  - pythonnet >= 3.0
  - User must be in "Siemens TIA Openness" Windows group
  - TIA Portal V19 installed
"""

import os
import sys
import tempfile
import traceback
from pathlib import Path
from datetime import datetime

# Default DLL path for TIA Portal V19
DEFAULT_DLL_PATH = (
    r"C:\Program Files\Siemens\Automation\Portal V19"
    r"\PublicAPI\V19\Siemens.Engineering.dll"
)

# Default project directory
DEFAULT_PROJECT_DIR = r"C:\TIA_Projects"

# CPU order numbers for hardware catalog lookup
# Format: "OrderNumber/Version"
CPU_ORDER_NUMBERS = {
    # S7-1200 series
    "CPU 1211C DC/DC/DC": "OrderNumber:6ES7 211-1AE40-0XB0/V4.6",
    "CPU 1211C AC/DC/Rly": "OrderNumber:6ES7 211-1BE40-0XB0/V4.6",
    "CPU 1212C DC/DC/DC": "OrderNumber:6ES7 212-1AE40-0XB0/V4.6",
    "CPU 1212C AC/DC/Rly": "OrderNumber:6ES7 212-1BE40-0XB0/V4.6",
    "CPU 1214C DC/DC/DC": "OrderNumber:6ES7 214-1AG40-0XB0/V4.6",
    "CPU 1214C AC/DC/Rly": "OrderNumber:6ES7 214-1BG40-0XB0/V4.6",
    "CPU 1215C DC/DC/DC": "OrderNumber:6ES7 215-1AG40-0XB0/V4.6",
    "CPU 1215C AC/DC/Rly": "OrderNumber:6ES7 215-1BG40-0XB0/V4.6",
    "CPU 1217C DC/DC/DC": "OrderNumber:6ES7 217-1AG40-0XB0/V4.6",
    # S7-1500 series
    "CPU 1511-1 PN": "OrderNumber:6ES7 511-1AK02-0AB0/V3.1",
    "CPU 1513-1 PN": "OrderNumber:6ES7 513-1AL02-0AB0/V3.1",
    "CPU 1515-2 PN": "OrderNumber:6ES7 515-2AM02-0AB0/V3.1",
    "CPU 1516-3 PN/DP": "OrderNumber:6ES7 516-3AN02-0AB0/V3.1",
    "CPU 1517-3 PN/DP": "OrderNumber:6ES7 517-3AP00-0AB0/V3.1",
    "CPU 1518-4 PN/DP": "OrderNumber:6ES7 518-4AP00-0AB0/V3.1",
    # S7-1500F (Failsafe)
    "CPU 1511F-1 PN": "OrderNumber:6ES7 511-1FK02-0AB0/V3.1",
    "CPU 1513F-1 PN": "OrderNumber:6ES7 513-1FL02-0AB0/V3.1",
    "CPU 1515F-2 PN": "OrderNumber:6ES7 515-2FM02-0AB0/V3.1",
    "CPU 1516F-3 PN/DP": "OrderNumber:6ES7 516-3FN02-0AB0/V3.1",
    "CPU 1518F-4 PN/DP": "OrderNumber:6ES7 518-4FP00-0AB0/V3.1",
}

# IO Module order numbers
IO_MODULE_ORDER_NUMBERS = {
    "DI 16x24VDC": "OrderNumber:6ES7 521-1BH10-0AA0/V2.0",
    "DI 32x24VDC": "OrderNumber:6ES7 521-1BL10-0AA0/V2.0",
    "DQ 16x24VDC/0.5A": "OrderNumber:6ES7 522-1BH10-0AA0/V2.0",
    "DQ 32x24VDC/0.5A": "OrderNumber:6ES7 522-1BL10-0AA0/V2.0",
    "AI 8xU/I/RTD/TC": "OrderNumber:6ES7 531-7KF00-0AB0/V2.0",
    "AI 4xU/I/RTD/TC": "OrderNumber:6ES7 531-7NF10-0AB0/V2.0",
    "AQ 4xU/I": "OrderNumber:6ES7 532-5HD00-0AB0/V2.0",
    "AQ 2xU/I": "OrderNumber:6ES7 532-5HF00-0AB0/V2.0",
}


class TIAHandler:
    """
    Wraps TIA Portal V19 Openness API operations.
    Uses pythonnet to call Siemens.Engineering.dll directly.
    """

    def __init__(self, dll_path=None, project_dir=None):
        self.dll_path = dll_path or os.environ.get("TIA_DLL_PATH", DEFAULT_DLL_PATH)
        self.project_dir = project_dir or os.environ.get("TIA_PROJECT_DIR", DEFAULT_PROJECT_DIR)
        self.portal = None
        self.project = None
        self._initialized = False
        self._log_lines = []

        # Ensure project directory exists
        Path(self.project_dir).mkdir(parents=True, exist_ok=True)

        # Load .NET assemblies
        self._init_dotnet()

    def _log(self, message):
        """Log a message with timestamp."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {message}"
        print(line)
        self._log_lines.append(line)
        # Keep last 500 log lines
        if len(self._log_lines) > 500:
            self._log_lines = self._log_lines[-500:]

    def _find_assembly_dirs(self):
        """
        Find all directories that may contain Siemens .NET assemblies.
        TIA Portal V19 scatters DLLs across multiple directories.
        The Contract DLL is often in the Bin folder, not the PublicAPI folder.
        """
        from pathlib import Path as _Path

        dirs = set()
        dll_dir = _Path(self.dll_path).parent
        dirs.add(str(dll_dir))

        # Common locations for Siemens.Engineering.Contract.dll and other deps
        tia_base = _Path(r"C:\Program Files\Siemens\Automation\Portal V19")

        search_paths = [
            dll_dir,
            dll_dir.parent,  # PublicAPI root
            tia_base / "Bin",
            tia_base / "Bin" / "Siemens.Engineering",
            tia_base / "Bin" / "PublicAPI",
            tia_base / "PublicAPI" / "V19",
            tia_base / "Hsp" / "Bin",
        ]

        for p in search_paths:
            if p.exists() and p.is_dir():
                dirs.add(str(p))

        # Also do a broader search: find all Siemens.Engineering.Contract.dll
        # under the TIA Portal installation
        try:
            for contract in tia_base.rglob("Siemens.Engineering.Contract.dll"):
                dirs.add(str(contract.parent))
                self._log(f"Found contract DLL at: {contract}")
        except Exception:
            pass

        return list(dirs)

    def _init_dotnet(self):
        """Initialize pythonnet and load Siemens.Engineering.dll."""
        try:
            import clr
            import sys as _sys
            from pathlib import Path as _Path

            # Discover all directories containing Siemens assemblies
            assembly_dirs = self._find_assembly_dirs()
            self._log(f"Assembly search directories: {assembly_dirs}")

            # Add all assembly dirs to Python path (helps pythonnet find DLLs)
            for d in assembly_dirs:
                if d not in _sys.path:
                    _sys.path.append(d)

            # Set up .NET assembly resolver BEFORE loading any DLLs.
            # This is critical — pythonnet needs to resolve dependent assemblies
            # (like Siemens.Engineering.Contract) when loading types.
            try:
                from System.Reflection import Assembly
                from System import AppDomain

                def resolve_handler(sender, args):
                    """Resolve missing assemblies from known TIA Portal directories."""
                    assembly_name = args.Name.split(',')[0]
                    for search_dir in assembly_dirs:
                        dll_file = _Path(search_dir) / f"{assembly_name}.dll"
                        if dll_file.exists():
                            try:
                                loaded = Assembly.LoadFrom(str(dll_file))
                                return loaded
                            except Exception:
                                continue
                    return None

                AppDomain.CurrentDomain.AssemblyResolve += resolve_handler
                self._log("Assembly resolver registered for all TIA directories")
            except Exception as resolver_err:
                self._log(f"Warning: Could not set up assembly resolver: {resolver_err}")

            # Pre-load contract and dependency DLLs BEFORE the main DLL
            # This ensures they're already in the AppDomain when needed
            preload_assemblies = [
                "Siemens.Engineering.Contract",
                "Siemens.Engineering.Hmi",
            ]
            for asm_name in preload_assemblies:
                for search_dir in assembly_dirs:
                    asm_path = _Path(search_dir) / f"{asm_name}.dll"
                    if asm_path.exists():
                        try:
                            clr.AddReference(str(asm_path))
                            self._log(f"Pre-loaded: {asm_path}")
                        except Exception as e:
                            self._log(f"Note: Could not pre-load {asm_name}: {e}")
                        break

            # Now load the main Siemens.Engineering.dll
            clr.AddReference(self.dll_path)
            self._log(f"Loaded main DLL: {self.dll_path}")

            # Import Siemens.Engineering namespaces
            # These become available after AddReference
            global TiaPortal, TiaPortalMode, Project
            global PlcSoftware, PlcBlock, PlcBlockGroup
            global DeviceItem, Device
            global CompilerResult

            from Siemens.Engineering import TiaPortal, TiaPortalMode
            from Siemens.Engineering import Project
            from Siemens.Engineering.SW.Blocks import PlcBlock, PlcBlockGroup
            from Siemens.Engineering.SW import PlcSoftware
            from Siemens.Engineering.HW import DeviceItem, Device
            from Siemens.Engineering.Compiler import CompilerResult

            self._initialized = True
            self._log(f"SUCCESS: All Siemens.Engineering types loaded!")

        except ImportError as e:
            self._log(f"ERROR: pythonnet not installed. Run: pip install pythonnet")
            self._log(f"Details: {e}")
            self._initialized = False

        except Exception as e:
            self._log(f"ERROR: Failed to load Siemens.Engineering.dll: {e}")
            self._log(f"DLL path: {self.dll_path}")
            self._log(f"Traceback: {traceback.format_exc()}")
            self._log(f"Make sure TIA Portal V19 is installed and the DLL exists.")
            self._log(f"Tip: Run this on Windows to find contract DLL location:")
            self._log(f'  dir /s "C:\\Program Files\\Siemens\\Automation\\Portal V19\\Siemens.Engineering.Contract.dll"')
            self._initialized = False

    def get_status(self) -> dict:
        """Get current status of TIA Portal connection."""
        project_name = None
        project_path = None
        blocks = []

        if self.project:
            try:
                project_name = self.project.Name
                project_path = str(self.project.Path)
            except Exception:
                # Project reference might be stale
                self.project = None

        return {
            "bridge": "online",
            "dll_loaded": self._initialized,
            "dll_path": self.dll_path,
            "tia_portal_connected": self.portal is not None,
            "project_open": self.project is not None,
            "project_name": project_name,
            "project_path": project_path,
            "timestamp": datetime.now().isoformat(),
        }

    def connect_or_launch(self, with_ui=True) -> dict:
        """Connect to a running TIA Portal instance or launch a new one."""
        if not self._initialized:
            return {"success": False, "message": "Siemens.Engineering.dll not loaded"}

        try:
            # First try to connect to existing instance
            self._log("Attempting to connect to existing TIA Portal instance...")
            processes = TiaPortal.GetProcesses()

            if processes.Count > 0:
                self._log(f"Found {processes.Count} running TIA Portal instance(s)")
                self.portal = processes[0].Attach()
                self._log("Attached to existing TIA Portal instance")

                # Check if a project is already open
                if self.portal.Projects.Count > 0:
                    self.project = self.portal.Projects[0]
                    self._log(f"Found open project: {self.project.Name}")

                return {
                    "success": True,
                    "message": "Connected to existing TIA Portal instance",
                    "new_instance": False,
                    "project_open": self.project is not None,
                    "project_name": self.project.Name if self.project else None,
                }

            # No running instance, launch a new one
            self._log("No running TIA Portal found. Launching new instance...")
            mode = TiaPortalMode.WithUserInterface if with_ui else TiaPortalMode.WithoutUserInterface
            self.portal = TiaPortal(mode)
            self._log("TIA Portal launched successfully")

            return {
                "success": True,
                "message": "Launched new TIA Portal instance",
                "new_instance": True,
                "project_open": False,
            }

        except Exception as e:
            self._log(f"ERROR connecting to TIA Portal: {e}")
            traceback.print_exc()
            return {
                "success": False,
                "message": f"Failed to connect: {str(e)}",
                "hint": "Ensure your user is in the 'Siemens TIA Openness' group",
            }

    def create_project(self, name, cpu_model="CPU 1214C DC/DC/DC") -> dict:
        """Create a new TIA Portal project with a PLC device."""
        if not self.portal:
            return {"success": False, "message": "Not connected to TIA Portal. Call /api/connect first."}

        try:
            # Close existing project if open
            if self.project:
                self._log(f"Closing current project: {self.project.Name}")
                self.project.Close()
                self.project = None

            # Create project directory
            project_path = Path(self.project_dir) / name
            project_path.mkdir(parents=True, exist_ok=True)

            self._log(f"Creating project '{name}' at {project_path}")

            # Create the project
            from System.IO import DirectoryInfo
            project_dir_info = DirectoryInfo(str(project_path))
            self.project = self.portal.Projects.Create(project_dir_info, name)

            self._log(f"Project created: {self.project.Name}")

            # Add PLC device
            device_info = self._add_plc_device(cpu_model)

            return {
                "success": True,
                "message": f"Project '{name}' created with {cpu_model}",
                "project_name": name,
                "project_path": str(project_path),
                "device": device_info,
            }

        except Exception as e:
            self._log(f"ERROR creating project: {e}")
            traceback.print_exc()
            return {"success": False, "message": f"Failed to create project: {str(e)}"}

    def _add_plc_device(self, cpu_model) -> dict:
        """Add a PLC device to the current project."""
        if not self.project:
            return {"success": False, "message": "No project open"}

        try:
            # Look up the order number for this CPU
            order_number = CPU_ORDER_NUMBERS.get(cpu_model)
            if not order_number:
                # Try partial match
                for key, val in CPU_ORDER_NUMBERS.items():
                    if cpu_model.lower() in key.lower():
                        order_number = val
                        cpu_model = key
                        break

            if not order_number:
                return {
                    "success": False,
                    "message": f"Unknown CPU model: {cpu_model}",
                    "available_cpus": list(CPU_ORDER_NUMBERS.keys()),
                }

            # Create device name from CPU model
            device_name = f"PLC_1"

            self._log(f"Adding device: {cpu_model} ({order_number})")

            # Add the device to the project
            # DeviceComposition.CreateWithItem(typeIdentifier, name, deviceName)
            device = self.project.Devices.CreateWithItem(
                order_number, device_name, device_name
            )

            self._log(f"Device added: {device.Name}")

            return {
                "success": True,
                "device_name": device.Name,
                "cpu_model": cpu_model,
                "order_number": order_number,
            }

        except Exception as e:
            self._log(f"ERROR adding device: {e}")
            traceback.print_exc()
            return {"success": False, "message": f"Failed to add device: {str(e)}"}

    def open_project(self, project_path) -> dict:
        """Open an existing TIA Portal project."""
        if not self.portal:
            return {"success": False, "message": "Not connected to TIA Portal"}

        try:
            # Close existing project
            if self.project:
                self.project.Close()
                self.project = None

            from System.IO import FileInfo
            project_file = FileInfo(project_path)

            self._log(f"Opening project: {project_path}")
            self.project = self.portal.Projects.Open(project_file)
            self._log(f"Project opened: {self.project.Name}")

            return {
                "success": True,
                "message": f"Opened project: {self.project.Name}",
                "project_name": self.project.Name,
                "project_path": str(self.project.Path),
            }

        except Exception as e:
            self._log(f"ERROR opening project: {e}")
            return {"success": False, "message": f"Failed to open project: {str(e)}"}

    def _get_plc_software(self):
        """Get the PlcSoftware instance from the first PLC device."""
        if not self.project:
            return None

        try:
            for device in self.project.Devices:
                for item in device.DeviceItems:
                    software_container = item.GetService[PlcSoftware]()
                    if software_container:
                        return software_container

                    # Check nested device items
                    for sub_item in item.DeviceItems:
                        software_container = sub_item.GetService[PlcSoftware]()
                        if software_container:
                            return software_container
        except Exception as e:
            self._log(f"Error finding PLC software: {e}")

        return None

    def configure_hardware(self, io_modules=None, profinet_ip=None) -> dict:
        """Configure hardware — add IO modules and set network parameters."""
        if not self.project:
            return {"success": False, "message": "No project open"}

        results = {"success": True, "modules_added": [], "network_configured": False}

        try:
            # Get the first device
            if self.project.Devices.Count == 0:
                return {"success": False, "message": "No devices in project"}

            device = self.project.Devices[0]

            # Add IO modules if specified
            if io_modules:
                for module_name in io_modules:
                    order_num = IO_MODULE_ORDER_NUMBERS.get(module_name)
                    if order_num:
                        try:
                            # Find the rack/rail to add the module to
                            for item in device.DeviceItems:
                                if hasattr(item, 'CanPlugNew') and item.CanPlugNew:
                                    item.PlugNew(order_num, module_name, -1)
                                    results["modules_added"].append(module_name)
                                    self._log(f"Added IO module: {module_name}")
                                    break
                        except Exception as e:
                            self._log(f"Warning: Could not add {module_name}: {e}")
                    else:
                        self._log(f"Unknown IO module: {module_name}")

            # Configure PROFINET IP if specified
            if profinet_ip:
                try:
                    for item in device.DeviceItems:
                        for sub_item in item.DeviceItems:
                            for iface in sub_item.DeviceItems:
                                network_service = iface.GetService[type(None)]()
                                if network_service and hasattr(network_service, 'Nodes'):
                                    for node in network_service.Nodes:
                                        node.SetAttribute("Address", profinet_ip)
                                        results["network_configured"] = True
                                        self._log(f"Set PROFINET IP: {profinet_ip}")
                except Exception as e:
                    self._log(f"Warning: Could not configure network: {e}")

            return results

        except Exception as e:
            self._log(f"ERROR configuring hardware: {e}")
            return {"success": False, "message": str(e)}

    def import_scl_block(self, block_name, scl_code) -> dict:
        """Import an SCL code block into the project."""
        if not self.project:
            return {"success": False, "message": "No project open"}

        plc_software = self._get_plc_software()
        if not plc_software:
            return {"success": False, "message": "No PLC software found in project"}

        try:
            # Save SCL to a temporary file
            temp_dir = Path(tempfile.gettempdir()) / "ladx_tia"
            temp_dir.mkdir(exist_ok=True)
            scl_file = temp_dir / f"{block_name}.scl"
            scl_file.write_text(scl_code, encoding="utf-8")

            self._log(f"Importing SCL block: {block_name} from {scl_file}")

            # Import via External Sources
            from System.IO import FileInfo
            file_info = FileInfo(str(scl_file))

            external_source_group = plc_software.ExternalSourceGroup
            external_source = external_source_group.ExternalSources.CreateFromFile(
                block_name, file_info
            )

            # Generate blocks from the external source
            self._log("Generating blocks from external source...")
            external_source.GenerateBlocksFromSource()

            # Clean up the external source entry (optional)
            try:
                external_source.Delete()
            except Exception:
                pass

            self._log(f"SCL block '{block_name}' imported successfully")

            return {
                "success": True,
                "message": f"Block '{block_name}' imported successfully",
                "block_name": block_name,
                "file_path": str(scl_file),
            }

        except Exception as e:
            self._log(f"ERROR importing SCL: {e}")
            traceback.print_exc()
            return {"success": False, "message": f"Import failed: {str(e)}"}

    def import_xml_block(self, xml_content, block_name="imported") -> dict:
        """Import a block from SimaticML XML (for LAD/FBD/etc)."""
        if not self.project:
            return {"success": False, "message": "No project open"}

        plc_software = self._get_plc_software()
        if not plc_software:
            return {"success": False, "message": "No PLC software found in project"}

        try:
            temp_dir = Path(tempfile.gettempdir()) / "ladx_tia"
            temp_dir.mkdir(exist_ok=True)
            xml_file = temp_dir / f"{block_name}.xml"
            xml_file.write_text(xml_content, encoding="utf-8")

            self._log(f"Importing XML block: {block_name}")

            from System.IO import FileInfo
            from Siemens.Engineering.SW.Blocks import ImportOptions

            file_info = FileInfo(str(xml_file))
            plc_software.BlockGroup.Blocks.Import(
                file_info, ImportOptions.Override
            )

            self._log(f"XML block '{block_name}' imported successfully")

            return {
                "success": True,
                "message": f"XML block '{block_name}' imported",
                "block_name": block_name,
            }

        except Exception as e:
            self._log(f"ERROR importing XML: {e}")
            traceback.print_exc()
            return {"success": False, "message": f"XML import failed: {str(e)}"}

    def compile_project(self) -> dict:
        """Compile the current project."""
        if not self.project:
            return {"success": False, "message": "No project open"}

        try:
            self._log("Compiling project...")

            # Get the compilable service from the project
            from Siemens.Engineering.Compiler import ICompilable

            errors = []
            warnings = []
            compile_success = True

            # Compile each device
            for device in self.project.Devices:
                for item in device.DeviceItems:
                    compilable = item.GetService[ICompilable]()
                    if compilable:
                        self._log(f"Compiling: {item.Name}")
                        result = compilable.Compile()

                        # Parse compile results
                        for msg in result.Messages:
                            if msg.State == CompilerResult.Error:
                                errors.append(str(msg))
                                compile_success = False
                            elif msg.State == CompilerResult.Warning:
                                warnings.append(str(msg))

            status = "success" if compile_success else "failed"
            self._log(f"Compilation {status}: {len(errors)} errors, {len(warnings)} warnings")

            return {
                "success": compile_success,
                "message": f"Compilation {status}",
                "errors": errors,
                "warnings": warnings,
                "error_count": len(errors),
                "warning_count": len(warnings),
            }

        except Exception as e:
            self._log(f"ERROR compiling: {e}")
            traceback.print_exc()
            return {"success": False, "message": f"Compilation failed: {str(e)}"}

    def download_to_plc(self, plc_ip="192.168.0.1", interface="PN/IE") -> dict:
        """Download the compiled project to a PLC."""
        if not self.project:
            return {"success": False, "message": "No project open"}

        try:
            self._log(f"Downloading to PLC at {plc_ip}...")

            from Siemens.Engineering.Download import IDownloadProvider
            from Siemens.Engineering.Download import DownloadConfiguration

            for device in self.project.Devices:
                for item in device.DeviceItems:
                    download_provider = item.GetService[IDownloadProvider]()
                    if download_provider:
                        # Configure download connection
                        config = download_provider.Configuration

                        # Find and configure the connection
                        for subnet_config in config.Modes:
                            for connection in subnet_config.PcInterfaces:
                                for target in connection.TargetInterfaces:
                                    self._log(f"Downloading via: {target.Name}")
                                    result = download_provider.Download(
                                        target,
                                        self._download_callback,
                                        DownloadConfiguration.AllowOnlyNewModules
                                    )

                                    self._log(f"Download result: {result.State}")

                                    return {
                                        "success": result.State.ToString() == "Success",
                                        "message": f"Download {result.State}",
                                        "plc_ip": plc_ip,
                                    }

            return {"success": False, "message": "No downloadable device found"}

        except Exception as e:
            self._log(f"ERROR downloading: {e}")
            traceback.print_exc()
            return {"success": False, "message": f"Download failed: {str(e)}"}

    def _download_callback(self, message):
        """Callback for download progress."""
        self._log(f"Download: {message}")

    def go_online(self, plc_ip="192.168.0.1") -> dict:
        """Establish an online connection to the PLC."""
        if not self.project:
            return {"success": False, "message": "No project open"}

        try:
            self._log(f"Going online with PLC at {plc_ip}...")

            from Siemens.Engineering.Online import IOnlineProvider

            for device in self.project.Devices:
                for item in device.DeviceItems:
                    online_provider = item.GetService[IOnlineProvider]()
                    if online_provider:
                        online_provider.GoOnline()
                        self._log("Online connection established")
                        return {
                            "success": True,
                            "message": "Online connection established",
                            "plc_ip": plc_ip,
                        }

            return {"success": False, "message": "No online-capable device found"}

        except Exception as e:
            self._log(f"ERROR going online: {e}")
            return {"success": False, "message": f"Go online failed: {str(e)}"}

    def list_blocks(self) -> dict:
        """List all program blocks in the project."""
        if not self.project:
            return {"success": False, "message": "No project open", "blocks": []}

        plc_software = self._get_plc_software()
        if not plc_software:
            return {"success": False, "message": "No PLC software found", "blocks": []}

        try:
            blocks = []
            self._enumerate_blocks(plc_software.BlockGroup, blocks)

            self._log(f"Found {len(blocks)} blocks")

            return {
                "success": True,
                "blocks": blocks,
                "count": len(blocks),
            }

        except Exception as e:
            self._log(f"ERROR listing blocks: {e}")
            return {"success": False, "message": str(e), "blocks": []}

    def _enumerate_blocks(self, block_group, blocks, path=""):
        """Recursively enumerate blocks in a block group."""
        try:
            for block in block_group.Blocks:
                blocks.append({
                    "name": block.Name,
                    "number": block.Number,
                    "type": block.GetType().Name,
                    "path": path,
                    "programming_language": str(block.ProgrammingLanguage) if hasattr(block, 'ProgrammingLanguage') else "Unknown",
                })

            # Recurse into subgroups
            for subgroup in block_group.Groups:
                self._enumerate_blocks(subgroup, blocks, f"{path}/{subgroup.Name}")

        except Exception as e:
            self._log(f"Warning: Error enumerating blocks: {e}")

    def export_block(self, block_name) -> dict:
        """Export a block as SimaticML XML."""
        if not self.project:
            return {"success": False, "message": "No project open"}

        plc_software = self._get_plc_software()
        if not plc_software:
            return {"success": False, "message": "No PLC software found"}

        try:
            # Find the block
            block = None
            for b in plc_software.BlockGroup.Blocks:
                if b.Name == block_name:
                    block = b
                    break

            if not block:
                return {"success": False, "message": f"Block '{block_name}' not found"}

            # Export to XML
            temp_dir = Path(tempfile.gettempdir()) / "ladx_tia"
            temp_dir.mkdir(exist_ok=True)
            xml_path = temp_dir / f"{block_name}.xml"

            from System.IO import FileInfo
            from Siemens.Engineering.SW.Blocks import ExportOptions

            block.Export(FileInfo(str(xml_path)), ExportOptions.WithDefaults)

            xml_content = xml_path.read_text(encoding="utf-8")

            self._log(f"Exported block: {block_name}")

            return {
                "success": True,
                "message": f"Exported {block_name}",
                "block_name": block_name,
                "xml": xml_content,
                "file_path": str(xml_path),
            }

        except Exception as e:
            self._log(f"ERROR exporting block: {e}")
            return {"success": False, "message": f"Export failed: {str(e)}"}

    def get_project_info(self) -> dict:
        """Get detailed information about the current project."""
        if not self.project:
            return {"success": False, "message": "No project open"}

        try:
            devices = []
            for device in self.project.Devices:
                device_info = {
                    "name": device.Name,
                    "type": device.TypeIdentifier if hasattr(device, 'TypeIdentifier') else "Unknown",
                    "items": [],
                }
                for item in device.DeviceItems:
                    device_info["items"].append({
                        "name": item.Name,
                        "type": item.GetType().Name,
                    })
                devices.append(device_info)

            # Get block count
            blocks_result = self.list_blocks()

            return {
                "success": True,
                "project_name": self.project.Name,
                "project_path": str(self.project.Path),
                "devices": devices,
                "device_count": len(devices),
                "block_count": blocks_result.get("count", 0),
            }

        except Exception as e:
            self._log(f"ERROR getting project info: {e}")
            return {"success": False, "message": str(e)}

    def close(self):
        """Close TIA Portal connection."""
        try:
            if self.project:
                self._log("Saving and closing project...")
                self.project.Save()
                self.project.Close()
                self.project = None

            if self.portal:
                self._log("Closing TIA Portal...")
                self.portal.Close()
                self.portal = None

            self._log("TIA Portal closed")
            return {"success": True, "message": "TIA Portal closed"}

        except Exception as e:
            self._log(f"ERROR closing: {e}")
            return {"success": False, "message": str(e)}

    def get_logs(self, count=50) -> list:
        """Get recent log lines."""
        return self._log_lines[-count:]
