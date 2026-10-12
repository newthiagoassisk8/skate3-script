#!/usr/bin/env python3
"""Abre Skate 3, conecta o controle e espelha o celular em outro scrcpy."""
import argparse
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

PACKAGE = "chat.buku.skate3"

def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", help="Serial ADB, se houver mais de um telefone")
    parser.add_argument(
        "--performance", action="store_true",
        help="Solicita modo desempenho e escala de 70%%; reinicia o jogo e mantém o ajuste no Android",
    )
    options = parser.parse_args()
    for tool in ("adb", "scrcpy"):
        if not shutil.which(tool):
            raise RuntimeError(f"Instale {tool} antes de continuar.")
    devices = [line.split()[0] for line in run("adb", "devices").splitlines()[1:]
               if len(line.split()) >= 2 and line.split()[1] == "device"]
    serial = options.serial
    if serial is None:
        if len(devices) != 1:
            raise RuntimeError("Conecte e autorize um telefone, ou informe --serial.")
        serial = devices[0]
    if serial not in devices:
        raise RuntimeError("Telefone desconectado ou ainda não autorizado.")
    def shell(*args):
        return run("adb", "-s", serial, "shell", *args)
    if not shell("pm", "path", PACKAGE).strip().startswith("package:"):
        raise RuntimeError("Skate 3 Mobile não está instalado neste telefone.")
    print(f"Telefone: {serial}", flush=True)
    if options.performance:
        print("Solicitando modo desempenho e escala de 70% para o jogo…", flush=True)
        try:
            for command in (
                ("cmd", "game", "set", "--mode", "performance", "--downscale", "0.7", PACKAGE),
                ("cmd", "game", "mode", "performance", PACKAGE),
            ):
                output = shell(*command).strip()
                if output:
                    print(output, flush=True)
                if re.search(r"error|exception|not supported|unsupported|unknown|invalid", output, re.I):
                    raise RuntimeError(output)
        except (subprocess.CalledProcessError, RuntimeError) as error:
            details = str(error)
            if isinstance(error, subprocess.CalledProcessError):
                details = (error.stderr or "") + (error.stdout or "")
            if not re.search(r"not supported|unsupported", details, re.I):
                raise
            print("Este aplicativo não aceita o ajuste pelo Android. Abrindo sem ele.", flush=True)
            print("Para reduzir os gráficos: RB + Start → Video → Android Device Profile "
                  "→ RG406V / Performance → Apply & Restart.", flush=True)
        else:
            # O Android exige reiniciar o aplicativo para aplicar a escala.
            shell("am", "force-stop", PACKAGE)
            print("Jogo reiniciado para aplicar o ajuste. Os FPS não foram alterados.", flush=True)
    result = shell("am", "start", "-n", f"{PACKAGE}/.LauncherActivity")
    if "Error" in result or "Exception" in result:
        raise RuntimeError(result)
    # A atividade do jogo é privada. Acionamos o botão visível do launcher.
    for _ in range(3):
        time.sleep(1)
        activities = shell("dumpsys", "activity", "activities")
        if re.search(r"(?:topResumedActivity|mResumedActivity|ResumedActivity).*"
                     + re.escape(PACKAGE) + r"/\.Skate3Activity", activities):
            break
        try:
            shell("uiautomator", "dump", "/data/local/tmp/skate3-launcher.xml")
            root = ET.fromstring(shell("cat", "/data/local/tmp/skate3-launcher.xml"))
        except (subprocess.CalledProcessError, ET.ParseError):
            print("Não consegui ler o launcher. Toque em Jogar no celular.", flush=True)
            break
        for node in root.iter("node"):
            label = node.get("text", "").strip().casefold()
            if label in ("play skate 3", "jogar skate 3", "play", "jogar") and node.get("enabled") == "true":
                bounds = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
                if bounds:
                    x1, y1, x2, y2 = map(int, bounds.groups())
                    try:
                        shell("input", "tap", str((x1+x2)//2), str((y1+y2)//2))
                    except subprocess.CalledProcessError:
                        print("Android bloqueou o toque por ADB. Toque em Jogar no celular.", flush=True)
                    break
    else:
        print("Não consegui confirmar a abertura do jogo. Toque em Jogar no celular.", flush=True)
    processes = []
    try:
        processes.append(subprocess.Popen([
            "scrcpy", f"--serial={serial}", "--no-video", "--no-audio", "--gamepad=uhid",
        ]))
        processes.append(subprocess.Popen([
            "scrcpy", f"--serial={serial}", "--no-control", "--no-audio",
            "--window-title=Skate 3 — Celular",
        ]))
        print("Controle e espelhamento ativos. Feche a janela ou use Ctrl+C para encerrar. "
              "O jogo e o áudio continuam no celular.", flush=True)
        while True:
            statuses = [process.poll() for process in processes]
            for process, status in zip(processes, statuses):
                if status is not None and status != 0:
                    raise subprocess.CalledProcessError(status, process.args)
            if any(status is not None for status in statuses):
                break
            time.sleep(0.2)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nControle e espelhamento encerrados.")
    except (RuntimeError, OSError, subprocess.CalledProcessError, ET.ParseError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            details = (error.stderr or error.stdout or "").strip()
            if details:
                print(details, file=sys.stderr)
        sys.exit(1)
