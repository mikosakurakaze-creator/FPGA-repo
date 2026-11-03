#!/usr/bin/env python3
"""Run a tool with ordinary desktop DLL lookup when a packaged host starts us.

Usage: python tools/run_windows_desktop.py -- EXECUTABLE ARGUMENTS...
Only the new process tree is affected. No registry, installation, PATH, or
project-source changes are made. This is not an elevation mechanism.
"""
import argparse
import os
import subprocess
import sys


def windows_package_name():
    import ctypes as c
    from ctypes import wintypes as w

    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentPackageFullName.argtypes = [c.POINTER(w.UINT), w.LPWSTR]
    length = w.UINT()
    status = kernel.GetCurrentPackageFullName(c.byref(length), None)
    if status == 15700:  # APPMODEL_ERROR_NO_PACKAGE
        return None
    if status != 122:  # ERROR_INSUFFICIENT_BUFFER
        raise c.WinError(status)
    name = c.create_unicode_buffer(length.value)
    status = kernel.GetCurrentPackageFullName(c.byref(length), name)
    if status:
        raise c.WinError(status)
    return name.value


def run_desktop_process(command):
    import ctypes as c
    from ctypes import wintypes as w
    import msvcrt

    class StartupInfo(c.Structure):
        _fields_ = [
            ("cb", w.DWORD), ("reserved", w.LPWSTR), ("desktop", w.LPWSTR),
            ("title", w.LPWSTR), ("x", w.DWORD), ("y", w.DWORD),
            ("x_size", w.DWORD), ("y_size", w.DWORD),
            ("x_chars", w.DWORD), ("y_chars", w.DWORD),
            ("fill", w.DWORD), ("flags", w.DWORD), ("show", w.WORD),
            ("reserved_size", w.WORD), ("reserved_ptr", c.c_void_p),
            ("stdin", w.HANDLE), ("stdout", w.HANDLE), ("stderr", w.HANDLE),
        ]

    class StartupInfoEx(c.Structure):
        _fields_ = [("info", StartupInfo), ("attributes", c.c_void_p)]

    class ProcessInfo(c.Structure):
        _fields_ = [("process", w.HANDLE), ("thread", w.HANDLE),
                    ("pid", w.DWORD), ("tid", w.DWORD)]

    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.InitializeProcThreadAttributeList.argtypes = [
        c.c_void_p, w.DWORD, w.DWORD, c.POINTER(c.c_size_t)]
    kernel.UpdateProcThreadAttribute.argtypes = [
        c.c_void_p, w.DWORD, c.c_size_t, c.c_void_p, c.c_size_t,
        c.c_void_p, c.c_void_p]
    kernel.DeleteProcThreadAttributeList.argtypes = [c.c_void_p]
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.GetStdHandle.argtypes = [w.DWORD]
    kernel.GetStdHandle.restype = w.HANDLE
    kernel.DuplicateHandle.argtypes = [
        w.HANDLE, w.HANDLE, w.HANDLE, c.POINTER(w.HANDLE),
        w.DWORD, w.BOOL, w.DWORD]
    kernel.CreateProcessW.argtypes = [
        w.LPCWSTR, w.LPWSTR, c.c_void_p, c.c_void_p, w.BOOL, w.DWORD,
        c.c_void_p, w.LPCWSTR, c.POINTER(StartupInfoEx), c.POINTER(ProcessInfo)]
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.GetExitCodeProcess.argtypes = [w.HANDLE, c.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes = [w.HANDLE]

    size = c.c_size_t()
    kernel.InitializeProcThreadAttributeList(None, 2, 0, c.byref(size))
    if not size.value:
        raise c.WinError(c.get_last_error())
    attributes = c.create_string_buffer(size.value)
    if not kernel.InitializeProcThreadAttributeList(attributes, 2, 0, c.byref(size)):
        raise c.WinError(c.get_last_error())

    duplicates, null_fds = [], []
    process = ProcessInfo()
    try:
        # PROC_THREAD_ATTRIBUTE_DESKTOP_APP_POLICY, enable desktop operation for
        # this child and its descendants. Windows enforces permission to do so.
        policy = w.DWORD(1)  # PROCESS_CREATION_DESKTOP_APP_BREAKAWAY_ENABLE_PROCESS_TREE
        if not kernel.UpdateProcThreadAttribute(
                attributes, 0, 0x00020012, c.byref(policy), c.sizeof(policy), None, None):
            raise c.WinError(c.get_last_error())

        current = kernel.GetCurrentProcess()
        for index, standard_id in enumerate((-10, -11, -12)):
            handle = kernel.GetStdHandle(standard_id & 0xffffffff)
            if handle in (None, c.c_void_p(-1).value):
                flags = os.O_RDONLY if index == 0 else os.O_WRONLY
                fd = os.open(os.devnull, flags | os.O_BINARY)
                null_fds.append(fd)
                handle = msvcrt.get_osfhandle(fd)
            duplicate = w.HANDLE()
            if not kernel.DuplicateHandle(
                    current, handle, current, c.byref(duplicate), 0, True, 2):
                raise c.WinError(c.get_last_error())
            duplicates.append(duplicate.value)

        # Inherit exactly stdin/stdout/stderr, preserving redirected log output.
        handles = (w.HANDLE * len(duplicates))(*duplicates)
        if not kernel.UpdateProcThreadAttribute(
                attributes, 0, 0x00020002, handles, c.sizeof(handles), None, None):
            raise c.WinError(c.get_last_error())
        startup = StartupInfoEx()
        startup.info.cb = c.sizeof(startup)
        startup.info.flags = 0x100  # STARTF_USESTDHANDLES
        startup.info.stdin, startup.info.stdout, startup.info.stderr = duplicates
        startup.attributes = c.cast(attributes, c.c_void_p)
        line = c.create_unicode_buffer(subprocess.list2cmdline(command))
        # Tool commands run without an extra console window. The environment,
        # working directory, user account, and privileges are inherited.
        if not kernel.CreateProcessW(
                None, line, None, None, True, 0x00080000 | 0x08000000,
                None, None, c.byref(startup), c.byref(process)):
            raise c.WinError(c.get_last_error())
        kernel.CloseHandle(process.thread)
        process.thread = None
        while True:
            result = kernel.WaitForSingleObject(process.process, 1000)
            if result == 0:
                break
            if result != 258:  # WAIT_TIMEOUT
                raise c.WinError(c.get_last_error())
        code = w.DWORD()
        if not kernel.GetExitCodeProcess(process.process, c.byref(code)):
            raise c.WinError(c.get_last_error())
        return code.value
    finally:
        if process.thread:
            kernel.CloseHandle(process.thread)
        if process.process:
            kernel.CloseHandle(process.process)
        for handle in duplicates:
            kernel.CloseHandle(handle)
        for fd in null_fds:
            os.close(fd)
        kernel.DeleteProcThreadAttributeList(attributes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("provide an executable and its arguments after --")
    try:
        package = windows_package_name() if os.name == "nt" else None
        if package:
            print("Desktop tool launch: leaving inherited package identity " + package,
                  file=sys.stderr, flush=True)
            return run_desktop_process(command)
        return subprocess.call(command)
    except OSError as error:
        print("Desktop tool launch failed: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
