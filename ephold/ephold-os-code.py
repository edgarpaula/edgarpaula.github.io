#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║          epHOLD OS — Código Fonte Completo v0.1          ║
║     Holder Edgar Paula · hold.edgarpaula.org             ║
╚══════════════════════════════════════════════════════════╝

Este arquivo agrupa todo o código Python do epHOLD OS para
fácil referência. Em produção, cada módulo fica no seu
próprio arquivo conforme a estrutura de diretórios.

ESTRUTURA:
  /opt/ephold/
  ├── core/
  │   ├── config.py      ← Leitura do epHOLD.conf
  │   ├── daemon.py      ← Loop principal
  │   ├── monitor.py     ← Health check e auto-restart
  │   ├── logger.py      ← Logging configurável
  │   └── backup.py      ← Backup de dados críticos
  ├── services/
  │   ├── bitcoin.py     ← Interface com Floresta
  │   ├── lightning.py   ← Interface com LND
  │   └── nostr.py       ← Interface com nostr-rs-relay
  ├── cli/
  │   └── cli.py         ← Ponto de entrada CLI
  └── config/
      └── epHOLD.conf    ← Configuração central (INI)
"""

# ═══════════════════════════════════════════════════════════
# ARQUIVO: config/epHOLD.conf
# ═══════════════════════════════════════════════════════════
EPHOLD_CONF_EXAMPLE = """
# epHOLD OS — Configuração Central
# Edite com: nano /opt/ephold/config/epHOLD.conf

[general]
node_name        = epHOLD-Node-01
data_dir         = /opt/ephold/data
log_dir          = /opt/ephold/logs
log_level        = INFO             # DEBUG | INFO | WARNING | ERROR
auto_restart     = true
restart_delay    = 30               # segundos antes de reiniciar serviço com falha
monitor_interval = 30               # intervalo entre verificações (segundos)

[bitcoin]
enabled          = true
network          = mainnet          # mainnet | testnet | signet
service_name     = floresta
rpc_host         = 127.0.0.1
rpc_port         = 8332

[lightning]
enabled          = true
service_name     = lnd
rpc_host         = 127.0.0.1
grpc_port        = 10009
rest_port        = 8080
mode             = neutrino

[nostr]
enabled          = true
service_name     = nostr-relay
host             = 0.0.0.0
port             = 7777
max_conn         = 100

[security]
# Chave pública age para criptografar backups
# Gere com: age-keygen -o ~/.age/ephhold.key
backup_key       =

[tor]
enabled          = false
socks_port       = 9050
"""

# ═══════════════════════════════════════════════════════════
# ARQUIVO: core/config.py
# ═══════════════════════════════════════════════════════════
CONFIG_PY = '''
"""
epHOLD OS — Módulo de Configuração
Lê e valida o arquivo epHOLD.conf central.
"""

import configparser
import os
from pathlib import Path

CONFIG_PATH = Path("/opt/ephold/config/epHOLD.conf")


class EPHoldConfig:
    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self._cfg = configparser.ConfigParser()
        self._load()

    def _load(self):
        if not self.path.exists():
            raise FileNotFoundError(
                f"Config não encontrado: {self.path}\\n"
                "Execute: ephold init"
            )
        self._cfg.read(self.path)

    def get(self, section: str, key: str, fallback=None):
        return self._cfg.get(section, key, fallback=fallback)

    def getbool(self, section: str, key: str, fallback=False):
        return self._cfg.getboolean(section, key, fallback=fallback)

    def getint(self, section: str, key: str, fallback=0):
        return self._cfg.getint(section, key, fallback=fallback)

    @property
    def services_enabled(self) -> list[str]:
        """Retorna lista de serviços habilitados no config."""
        enabled = []
        for section in ["bitcoin", "lightning", "nostr"]:
            if self.getbool(section, "enabled"):
                enabled.append(self.get(section, "service_name"))
        return enabled


# Instância global — use em todo o projeto
config = EPHoldConfig()
'''

# ═══════════════════════════════════════════════════════════
# ARQUIVO: core/logger.py
# ═══════════════════════════════════════════════════════════
LOGGER_PY = '''
"""
epHOLD OS — Configuração de Logging
Centraliza logs em arquivo e stdout com formatação consistente.
"""

import logging
import sys
from pathlib import Path


def setup_logging(log_dir: str = "/opt/ephold/logs",
                  log_level: str = "INFO") -> logging.Logger:
    """
    Configura o sistema de logging do epHOLD OS.
    Retorna o logger raiz configurado.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, log_level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Handler: arquivo rotativo simples
    file_handler = logging.FileHandler(log_path / "ephold.log")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # Handler: stdout com cores
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColorFormatter(formatter))
    console_handler.setLevel(level)

    root = logging.getLogger("ephold")
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    root.propagate = False

    return root


class ColorFormatter(logging.Formatter):
    """Adiciona cores ANSI ao output do console."""
    COLORS = {
        logging.DEBUG:    "\\033[37m",   # cinza
        logging.INFO:     "\\033[92m",   # verde
        logging.WARNING:  "\\033[93m",   # amarelo
        logging.ERROR:    "\\033[91m",   # vermelho
        logging.CRITICAL: "\\033[95m",   # magenta
    }
    RESET = "\\033[0m"

    def __init__(self, base_formatter: logging.Formatter):
        super().__init__()
        self._base = base_formatter

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, "")
        msg = self._base.format(record)
        return f"{color}{msg}{self.RESET}"
'''

# ═══════════════════════════════════════════════════════════
# ARQUIVO: core/monitor.py
# ═══════════════════════════════════════════════════════════
MONITOR_PY = '''
"""
epHOLD OS — Monitor de Serviços
Verifica saúde e reinicia serviços com falha via systemctl.
Estratégia: exponential backoff nos restarts para evitar loops.
"""

import subprocess
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger("ephold.monitor")


class ServiceState(Enum):
    ACTIVE   = "active"
    INACTIVE = "inactive"
    FAILED   = "failed"
    UNKNOWN  = "unknown"


@dataclass
class ServiceStatus:
    name:        str
    state:       ServiceState
    pid:         str = ""
    uptime:      str = ""
    last_check:  datetime = field(default_factory=datetime.now)
    restart_count: int = 0


# Estado global dos serviços (persistido em memória durante o daemon)
_service_registry: dict[str, ServiceStatus] = {}


def check_service(service_name: str) -> ServiceStatus:
    """Consulta estado de um serviço systemd."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True, text=True, timeout=5
        )
        raw = result.stdout.strip()
        state = ServiceState(raw) if raw in [s.value for s in ServiceState] \
                else ServiceState.UNKNOWN

        # Atualizar registro
        prev = _service_registry.get(service_name)
        status = ServiceStatus(
            name=service_name,
            state=state,
            last_check=datetime.now(),
            restart_count=prev.restart_count if prev else 0
        )
        _service_registry[service_name] = status
        return status

    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout ao verificar {service_name}")
        return ServiceStatus(name=service_name, state=ServiceState.UNKNOWN)


def restart_service(service_name: str, delay: int = 30) -> bool:
    """
    Reinicia um serviço systemd.
    Aplica delay configurável e registra número de restarts.
    """
    status = _service_registry.get(service_name)
    if status:
        status.restart_count += 1
        # Exponential backoff: máximo de 5 minutos
        effective_delay = min(delay * (2 ** (status.restart_count - 1)), 300)
    else:
        effective_delay = delay

    logger.warning(
        f"⚠ Reiniciando {service_name} "
        f"(tentativa #{status.restart_count if status else 1}, "
        f"aguardando {effective_delay}s)"
    )
    time.sleep(effective_delay)

    try:
        result = subprocess.run(
            ["systemctl", "restart", service_name],
            capture_output=True, text=True, timeout=60
        )
        success = result.returncode == 0
        if success:
            logger.info(f"✓ {service_name} reiniciado com sucesso")
            if status:
                status.restart_count = 0  # reset após sucesso
        else:
            logger.error(f"✗ Falha ao reiniciar {service_name}: {result.stderr.strip()}")
        return success

    except subprocess.TimeoutExpired:
        logger.error(f"Timeout ao reiniciar {service_name}")
        return False


def get_all_status() -> list[ServiceStatus]:
    """Retorna status de todos os serviços monitorados."""
    return list(_service_registry.values())


def monitor_loop(services: list[str],
                 interval: int = 30,
                 restart_delay: int = 30,
                 auto_restart: bool = True):
    """
    Loop principal de monitoramento.
    Verifica cada serviço e reinicia automaticamente em caso de falha.

    Args:
        services:      Lista de nomes de serviço systemd
        interval:      Segundos entre cada ciclo de verificação
        restart_delay: Delay base antes de reiniciar (exponential backoff)
        auto_restart:  Se False, apenas loga sem reiniciar
    """
    logger.info(f"Monitor iniciado. Serviços: {services} | Intervalo: {interval}s")

    while True:
        for svc in services:
            status = check_service(svc)

            if status.state == ServiceState.ACTIVE:
                logger.debug(f"[OK] {svc} ativo")

            elif status.state in (ServiceState.FAILED, ServiceState.INACTIVE):
                logger.error(f"[FALHA] {svc} está {status.state.value}")
                if auto_restart:
                    restart_service(svc, delay=restart_delay)
                else:
                    logger.warning("Auto-restart desabilitado no config.")

            else:
                logger.warning(f"[?] {svc} estado desconhecido")

        time.sleep(interval)
'''

# ═══════════════════════════════════════════════════════════
# ARQUIVO: core/daemon.py
# ═══════════════════════════════════════════════════════════
DAEMON_PY = '''
"""
epHOLD OS — Daemon Principal
Inicializa o sistema, lê config e inicia o monitor.
Registre como: ephold-daemon.service no systemd.
"""

import logging
import threading
import signal
import sys
from core.config import config
from core.logger import setup_logging
from core.monitor import monitor_loop


def handle_signal(signum, frame):
    logging.getLogger("ephold").info(
        f"Sinal {signum} recebido — encerrando daemon gracefully..."
    )
    sys.exit(0)


def start_daemon():
    # Configurar logging primeiro
    log_dir    = config.get("general", "log_dir", fallback="/opt/ephold/logs")
    log_level  = config.get("general", "log_level", fallback="INFO")
    setup_logging(log_dir=log_dir, log_level=log_level)

    logger = logging.getLogger("ephold")
    logger.info("═" * 50)
    logger.info("  epHOLD OS Daemon iniciando")
    logger.info(f"  Node: {config.get('general', 'node_name', fallback='epHOLD')}")
    logger.info("═" * 50)

    # Capturar sinais POSIX para shutdown limpo
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT,  handle_signal)

    # Ler parâmetros do config
    services      = config.services_enabled
    interval      = config.getint("general", "monitor_interval", fallback=30)
    restart_delay = config.getint("general", "restart_delay",    fallback=30)
    auto_restart  = config.getbool("general", "auto_restart",    fallback=True)

    if not services:
        logger.warning("Nenhum serviço habilitado no config. Encerrando.")
        sys.exit(1)

    logger.info(f"Serviços habilitados: {services}")

    # Iniciar monitor em thread daemon
    monitor_thread = threading.Thread(
        target=monitor_loop,
        args=(services, interval, restart_delay, auto_restart),
        daemon=True,
        name="ephold-monitor"
    )
    monitor_thread.start()
    logger.info("Monitor iniciado em thread background.")

    # Manter o processo vivo
    monitor_thread.join()


if __name__ == "__main__":
    start_daemon()
'''

# ═══════════════════════════════════════════════════════════
# ARQUIVO: core/backup.py
# ═══════════════════════════════════════════════════════════
BACKUP_PY = '''
"""
epHOLD OS — Backup Automático
Copia e criptografa dados críticos do Lightning e configurações.
Requer: age (https://age-encryption.org) para criptografia.
"""

import subprocess
import shutil
import logging
from datetime import datetime
from pathlib import Path
from core.config import config

logger = logging.getLogger("ephold.backup")

LND_DIR    = Path("/opt/ephold/data/lnd")
BACKUP_DIR = Path("/opt/ephold/backups")

# Arquivos críticos a fazer backup
CRITICAL_FILES = [
    "data/chain/bitcoin/mainnet/channel.backup",
    "tls.cert",
    "admin.macaroon",
]


def backup_lnd() -> list[Path]:
    """Copia arquivos críticos do LND para diretório de backup."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_subdir = BACKUP_DIR / f"lnd_{ts}"
    backup_subdir.mkdir()

    backed_up = []
    for rel_path in CRITICAL_FILES:
        src = LND_DIR / rel_path
        if src.exists():
            dest = backup_subdir / src.name
            shutil.copy2(src, dest)
            logger.info(f"✓ Backup: {src.name}")
            backed_up.append(dest)
        else:
            logger.warning(f"Não encontrado: {src}")

    return backed_up


def create_archive(files: list[Path], archive_name: str) -> Path:
    """Cria arquivo tar.gz com os arquivos de backup."""
    archive = BACKUP_DIR / f"{archive_name}.tar.gz"
    import tarfile
    with tarfile.open(archive, "w:gz") as tar:
        for f in files:
            tar.add(f, arcname=f.name)
    logger.info(f"✓ Arquivo criado: {archive}")
    return archive


def encrypt_with_age(path: Path, recipient_key: str) -> Path:
    """
    Criptografa arquivo com age.
    recipient_key: chave pública age (age1...)
    """
    out = path.with_suffix(".age")
    try:
        subprocess.run(
            ["age", "-r", recipient_key, "-o", str(out), str(path)],
            check=True, capture_output=True
        )
        path.unlink()  # Remover versão não criptografada
        logger.info(f"✓ Criptografado: {out.name}")
        return out
    except FileNotFoundError:
        logger.error(
            "age não encontrado. Instale: apt install age\\n"
            "Backup salvo SEM CRIPTOGRAFIA — proteja o arquivo manualmente!"
        )
        return path
    except subprocess.CalledProcessError as e:
        logger.error(f"Erro ao criptografar: {e.stderr}")
        return path


def run_backup():
    """Ponto de entrada — executa backup completo."""
    logger.info("Iniciando backup de dados críticos do epHOLD OS...")

    # 1. Copiar arquivos
    files = backup_lnd()
    if not files:
        logger.error("Nenhum arquivo de backup encontrado.")
        return

    # 2. Criar arquivo comprimido
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = create_archive(files, f"ephold_backup_{ts}")

    # 3. Criptografar se chave configurada
    age_key = config.get("security", "backup_key", fallback=None)
    if age_key:
        encrypt_with_age(archive, age_key)
    else:
        logger.warning(
            "backup_key não configurado em epHOLD.conf [security].\\n"
            "Configure: age-keygen -o ~/.age/ephold.key"
        )

    logger.info("Backup concluído.")


if __name__ == "__main__":
    from core.logger import setup_logging
    setup_logging()
    run_backup()
'''

# ═══════════════════════════════════════════════════════════
# ARQUIVO: services/bitcoin.py
# ═══════════════════════════════════════════════════════════
BITCOIN_PY = '''
"""
epHOLD OS — Interface com Floresta (Bitcoin node)
Consulta informações do node via RPC JSON.
"""

import logging
import requests
from core.config import config

logger = logging.getLogger("ephold.bitcoin")


class FlorestaClient:
    """Cliente simples para o RPC do Floresta."""

    def __init__(self):
        host = config.get("bitcoin", "rpc_host", fallback="127.0.0.1")
        port = config.getint("bitcoin", "rpc_port", fallback=8332)
        self.base_url = f"http://{host}:{port}"
        self._id = 0

    def _rpc(self, method: str, params: list = None) -> dict:
        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._id,
            "method": method,
            "params": params or []
        }
        try:
            resp = requests.post(
                self.base_url,
                json=payload,
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            if "error" in data and data["error"]:
                raise RuntimeError(f"RPC error: {data['error']}")
            return data.get("result", {})
        except requests.ConnectionError:
            logger.error("Floresta não acessível via RPC")
            return {}

    def get_blockchain_info(self) -> dict:
        """Retorna informações gerais da blockchain."""
        return self._rpc("getblockchaininfo")

    def get_block_count(self) -> int:
        """Retorna altura atual do bloco."""
        result = self._rpc("getblockcount")
        return int(result) if result else 0

    def get_network_info(self) -> dict:
        """Retorna informações de rede e peers."""
        return self._rpc("getnetworkinfo")

    def is_synced(self) -> bool:
        """Verifica se o node está sincronizado."""
        info = self.get_blockchain_info()
        progress = info.get("verificationprogress", 0)
        return progress > 0.9999


# Instância global
floresta = FlorestaClient()
'''

# ═══════════════════════════════════════════════════════════
# ARQUIVO: services/lightning.py
# ═══════════════════════════════════════════════════════════
LIGHTNING_PY = '''
"""
epHOLD OS — Interface com LND (Lightning Network Daemon)
Usa a API REST do LND para consultas básicas.
Requer: macaroon com permissões de leitura.
"""

import logging
import base64
import requests
from pathlib import Path
from core.config import config

logger = logging.getLogger("ephold.lightning")

LND_DIR = Path("/opt/ephold/data/lnd")


class LNDClient:
    """Cliente REST para o LND."""

    def __init__(self):
        host = config.get("lightning", "rpc_host", fallback="127.0.0.1")
        port = config.getint("lightning", "rest_port", fallback=8080)
        self.base_url = f"https://{host}:{port}"
        self._setup_tls()

    def _setup_tls(self):
        """Configura certificado TLS e macaroon do LND."""
        self.tls_cert = str(LND_DIR / "tls.cert")
        macaroon_path = LND_DIR / "data/chain/bitcoin/mainnet/readonly.macaroon"
        if macaroon_path.exists():
            with open(macaroon_path, "rb") as f:
                self.macaroon = f.read().hex()
        else:
            logger.warning("Macaroon LND não encontrado — LND inicializado?")
            self.macaroon = None

    def _get(self, endpoint: str) -> dict:
        if not self.macaroon:
            return {}
        headers = {"Grpc-Metadata-macaroon": self.macaroon}
        try:
            resp = requests.get(
                f"{self.base_url}/v1/{endpoint}",
                headers=headers,
                verify=self.tls_cert,
                timeout=10
            )
            resp.raise_for_status()
            return resp.json()
        except requests.ConnectionError:
            logger.error("LND REST API não acessível")
            return {}

    def get_info(self) -> dict:
        """Retorna informações do node LND."""
        return self._get("getinfo")

    def get_channels(self) -> list:
        """Lista canais Lightning ativos."""
        result = self._get("channels")
        return result.get("channels", [])

    def get_balance(self) -> dict:
        """Retorna saldo on-chain e Lightning."""
        onchain  = self._get("balance/blockchain")
        channels = self._get("balance/channels")
        return {
            "onchain_confirmed":  onchain.get("confirmed_balance", 0),
            "onchain_unconfirmed": onchain.get("unconfirmed_balance", 0),
            "lightning_local":    channels.get("local_balance", {}).get("sat", 0),
            "lightning_remote":   channels.get("remote_balance", {}).get("sat", 0),
        }

    def get_node_pubkey(self) -> str:
        """Retorna a chave pública do node."""
        info = self.get_info()
        return info.get("identity_pubkey", "N/A")


# Instância global
lnd = LNDClient()
'''

# ═══════════════════════════════════════════════════════════
# ARQUIVO: cli/cli.py
# ═══════════════════════════════════════════════════════════
CLI_PY = '''
#!/usr/bin/env python3
"""
epHOLD OS — Interface de Linha de Comando
Uso: ephold <comando> [opções]

Comandos:
  status          Status de todos os serviços
  start [svc]     Iniciar serviço(s)
  stop  [svc]     Parar serviço(s)
  restart [svc]   Reiniciar serviço(s)
  logs [svc] -n N Ver N linhas de log
  info            Informações do node
  backup          Fazer backup manual
"""

import argparse
import subprocess
import sys
from core.config import config
from core.monitor import check_service, ServiceState, get_all_status

# Adicionar /opt/ephold ao path para imports relativos
import os
sys.path.insert(0, "/opt/ephold")

BANNER = """\\033[93m
  ___  _  _  _  _  ___  _    ____      ___  ____
 | __|| \\| || || || __|| |  |    \\    / _ \\/ ___|
 | _| | .` || __ || _| | |__| |) |  | (_) \\__  \\
 |___||_|\\_||_||_||___||____|___/    \\___/|____/
\\033[0m
  \\033[90mSoberania Digital · hold.edgarpaula.org\\033[0m
"""

STATE_ICON = {
    ServiceState.ACTIVE:   ("\\033[92m●\\033[0m", "\\033[92mativo\\033[0m"),
    ServiceState.INACTIVE: ("\\033[90m●\\033[0m", "\\033[90minativo\\033[0m"),
    ServiceState.FAILED:   ("\\033[91m●\\033[0m", "\\033[91mfalha\\033[0m"),
    ServiceState.UNKNOWN:  ("\\033[93m●\\033[0m", "\\033[93mdesconhecido\\033[0m"),
}


# ── HANDLERS ──────────────────────────────────────────────

def cmd_status(args):
    """Mostra status de todos os serviços."""
    print(BANNER)
    print("  Serviços\\n")
    services = config.services_enabled
    for svc in services:
        st = check_service(svc)
        icon, state_str = STATE_ICON.get(st.state, ("?", "?"))
        print(f"  {icon}  {svc:<25} {state_str}")
    print()


def cmd_start(args):
    targets = [args.service] if args.service else config.services_enabled
    for svc in targets:
        print(f"  ▶ Iniciando {svc}...")
        result = subprocess.run(["systemctl", "start", svc], capture_output=True)
        if result.returncode == 0:
            print(f"  \\033[92m✓ {svc} iniciado\\033[0m")
        else:
            print(f"  \\033[91m✗ Falha: {result.stderr.decode().strip()}\\033[0m")


def cmd_stop(args):
    targets = [args.service] if args.service else config.services_enabled
    for svc in targets:
        print(f"  ■ Parando {svc}...")
        subprocess.run(["systemctl", "stop", svc])


def cmd_restart(args):
    targets = [args.service] if args.service else config.services_enabled
    for svc in targets:
        print(f"  ↺ Reiniciando {svc}...")
        result = subprocess.run(["systemctl", "restart", svc], capture_output=True)
        if result.returncode == 0:
            print(f"  \\033[92m✓ {svc} reiniciado\\033[0m")
        else:
            print(f"  \\033[91m✗ Falha: {result.stderr.decode().strip()}\\033[0m")


def cmd_logs(args):
    svc   = args.service or "ephold-daemon"
    lines = args.lines or 50
    subprocess.run(["journalctl", "-u", svc, "-n", str(lines), "--no-pager"])


def cmd_info(args):
    node = config.get("general", "node_name", fallback="epHOLD")
    net  = config.get("bitcoin", "network",   fallback="mainnet")
    ver  = "0.1.0"
    print(f"""
  \\033[93mepHOLD OS v{ver}\\033[0m
  ─────────────────────────────
  Node:    {node}
  Rede:    {net}
  Config:  /opt/ephold/config/epHOLD.conf
  Logs:    /opt/ephold/logs/ephold.log
  Web:     hold.edgarpaula.org
""")


def cmd_backup(args):
    print("  Iniciando backup...")
    try:
        from core.backup import run_backup
        run_backup()
        print("  \\033[92m✓ Backup concluído\\033[0m")
    except Exception as e:
        print(f"  \\033[91m✗ Erro no backup: {e}\\033[0m")


# ── MAIN ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="ephold",
        description="epHOLD OS — CLI de Soberania Digital",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", metavar="<comando>")

    sub.add_parser("status", help="Status dos serviços")

    p = sub.add_parser("start",   help="Iniciar serviço(s)")
    p.add_argument("service", nargs="?", help="Nome do serviço (omita para todos)")

    p = sub.add_parser("stop",    help="Parar serviço(s)")
    p.add_argument("service", nargs="?")

    p = sub.add_parser("restart", help="Reiniciar serviço(s)")
    p.add_argument("service", nargs="?")

    p = sub.add_parser("logs",    help="Ver logs de um serviço")
    p.add_argument("service", nargs="?", help="Nome do serviço (padrão: daemon)")
    p.add_argument("-n", "--lines", type=int, default=50, help="Número de linhas")

    sub.add_parser("info",        help="Informações do node")
    sub.add_parser("backup",      help="Executar backup manual")

    args = parser.parse_args()

    handlers = {
        "status":  cmd_status,
        "start":   cmd_start,
        "stop":    cmd_stop,
        "restart": cmd_restart,
        "logs":    cmd_logs,
        "info":    cmd_info,
        "backup":  cmd_backup,
    }

    handler = handlers.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
'''

# ═══════════════════════════════════════════════════════════
# ARQUIVO: install.sh
# ═══════════════════════════════════════════════════════════
INSTALL_SH = '''#!/bin/bash
# ══════════════════════════════════════════════════
#  epHOLD OS — Instalador Automático v0.1
#  Uso: curl -sSL https://hold.edgarpaula.org/install.sh | bash
# ══════════════════════════════════════════════════

set -euo pipefail

INSTALL_DIR="/opt/ephold"
EPHOLD_USER="ephold"
PYTHON="python3"
REPO_URL="https://github.com/edgarpaula/ephold-os"

RED=\'\\033[91m\'
GREEN=\'\\033[92m\'
YELLOW=\'\\033[93m\'
RESET=\'\\033[0m\'

ok()   { echo "${GREEN}✓${RESET} $1"; }
warn() { echo "${YELLOW}⚠${RESET} $1"; }
err()  { echo "${RED}✗${RESET} $1"; exit 1; }

echo ""
echo "  ╔═══════════════════════════════════╗"
echo "  ║    epHOLD OS — Instalador v0.1    ║"
echo "  ║    hold.edgarpaula.org            ║"
echo "  ╚═══════════════════════════════════╝"
echo ""

# Verificar root
[[ "$EUID" -ne 0 ]] && err "Execute como root: sudo bash install.sh"

# 1. Atualizar e instalar dependências
echo "Instalando dependências do sistema..."
apt-get update -qq
apt-get install -y --no-install-recommends \\
    python3 python3-pip git ufw curl wget \\
    build-essential pkg-config libssl-dev \\
    fail2ban unattended-upgrades age
ok "Dependências instaladas"

# 2. Criar usuário dedicado
if ! id "$EPHOLD_USER" &>/dev/null; then
    useradd -r -m -s /bin/bash "$EPHOLD_USER"
    ok "Usuário $EPHOLD_USER criado"
else
    warn "Usuário $EPHOLD_USER já existe"
fi

# 3. Clonar ou atualizar repositório
if [ -d "$INSTALL_DIR/.git" ]; then
    warn "Repositório já existe — atualizando..."
    cd "$INSTALL_DIR" && git pull -q
else
    git clone -q "$REPO_URL" "$INSTALL_DIR"
    ok "Repositório clonado em $INSTALL_DIR"
fi

# 4. Criar estrutura de diretórios
mkdir -p "$INSTALL_DIR"/{data/{floresta,lnd,nostr},logs,backups,config}
ok "Estrutura de diretórios criada"

# 5. Instalar dependências Python
"$PYTHON" -m pip install -r "$INSTALL_DIR/requirements.txt" -q 2>/dev/null || true
ok "Dependências Python instaladas"

# 6. Config padrão
if [ ! -f "$INSTALL_DIR/config/epHOLD.conf" ]; then
    cp "$INSTALL_DIR/config/epHOLD.conf.example" \\
       "$INSTALL_DIR/config/epHOLD.conf"
    ok "Config padrão criado"
else
    warn "Config já existe — não sobrescrito"
fi

# 7. Symlink CLI
ln -sf "$INSTALL_DIR/cli/cli.py" /usr/local/bin/ephold
chmod +x "$INSTALL_DIR/cli/cli.py"
ok "CLI disponível: ephold"

# 8. Permissões
chown -R "$EPHOLD_USER:$EPHOLD_USER" "$INSTALL_DIR"

# 9. Configuração básica de firewall
ufw --force reset > /dev/null
ufw default deny incoming > /dev/null
ufw default allow outgoing > /dev/null
ufw allow ssh > /dev/null
ufw allow 8333/tcp comment "Bitcoin P2P" > /dev/null
ufw allow 9735/tcp comment "Lightning" > /dev/null
ufw allow 7777/tcp comment "Nostr relay" > /dev/null
ufw --force enable > /dev/null
ok "Firewall configurado (ufw)"

echo ""
echo "  ══════════════════════════════════════"
echo "  epHOLD OS instalado com sucesso! ✓"
echo ""
echo "  Próximos passos:"
echo "  1. Edite a config: nano $INSTALL_DIR/config/epHOLD.conf"
echo "  2. Instale Floresta, LND e nostr-relay (ver docs)"
echo "  3. Execute: ephold status"
echo "  ══════════════════════════════════════"
echo ""
'''

# ═══════════════════════════════════════════════════════════
# ARQUIVO: ephold-daemon.service (systemd unit)
# ═══════════════════════════════════════════════════════════
SYSTEMD_SERVICE = """
[Unit]
Description=epHOLD OS Daemon — Monitor de Serviços
Documentation=https://hold.edgarpaula.org
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ephold
Group=ephold
WorkingDirectory=/opt/ephold
ExecStart=/usr/bin/python3 /opt/ephold/core/daemon.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ephold-daemon

# Segurança
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/opt/ephold/logs /opt/ephold/backups

[Install]
WantedBy=multi-user.target
"""

# ═══════════════════════════════════════════════════════════
# ARQUIVO: requirements.txt
# ═══════════════════════════════════════════════════════════
REQUIREMENTS = """
# epHOLD OS — Dependências Python
# Instalar: pip install -r requirements.txt

requests>=2.31.0       # HTTP client (LND REST API, Floresta RPC)
configparser>=5.3.0    # Leitura do epHOLD.conf (built-in, explícito por clareza)
"""


if __name__ == "__main__":
    print("epHOLD OS — Referência de código fonte v0.1")
    print("Consulte os comentários de cada seção para os caminhos dos arquivos.")
    print("Documentação: https://hold.edgarpaula.org")
