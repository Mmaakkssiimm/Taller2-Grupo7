#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Taller 2 - FidelizaBot (POO + SQLite, portable y sin dependencias externas)
--------------------------------------------------------------------------
Backend simple de puntos/recompensas para un café o tienda local.

✔ Enfoque académico para evaluar POO (herencia/polimorfismo) y arquitectura limpia.
✔ Persistencia con SQLite (stdlib) y resolución de ruta *robusta* multiplataforma.
✔ CLI mínima para demostrar end-to-end: alta de cliente, compras, redención, historial.

Ejecución:
  python src/Taller_2_FidelizaBot_Grupo_X.py
Requisitos: Python 3.10+ (no usa librerías externas)

NOTA IMPORTANTE SOBRE LA BASE DE DATOS
--------------------------------------
El programa guarda la base en:
  1) ./data/fidelizabot.db   (si el repo es escribible)
  2) Carpeta de datos del usuario (APPDATA / Library / ~/.local/share) si 1) no es posible
  3) Directorio de trabajo actual (como último intento)
  4) Modo memoria ':memory:' (no persistente) sólo si todo lo anterior falla (poco probable)
También puedes forzar una ruta con la variable de entorno FIDELIZABOT_DB.
"""

from __future__ import annotations

import os
import sys
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Tuple, Type

# =====================
#  Resolución DB robusta
# =====================

def _is_writable_dir(path: str) -> bool:
    """Devuelve True si 'path' existe o se puede crear y es escribible (prueba archivo temporal)."""
    try:
        os.makedirs(path, exist_ok=True)
        testfile = os.path.join(path, ".wtest")
        with open(testfile, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(testfile)
        return True
    except Exception:
        return False

def _user_data_dir(app_name: str = "FidelizaBot") -> str:
    """Devuelve una carpeta de datos por plataforma sin dependencias externas."""
    home = os.path.expanduser("~")
    if os.name == "nt":  # Windows
        base = os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
        return os.path.join(base, app_name)
    elif sys.platform == "darwin":  # macOS
        return os.path.join(home, "Library", "Application Support", app_name)
    else:  # Linux/Unix
        return os.path.join(home, ".local", "share", app_name)

def resolve_db_path(filename: str = "fidelizabot.db") -> str:
    """
    Prioriza:
      A) env FIDELIZABOT_DB
      B) ./data/<filename> en el directorio del proyecto
      C) carpeta de datos del usuario
      D) cwd (último intento)
      E) ':memory:' (fallback final no persistente)
    """
    # A) Variable de entorno
    env_path = os.environ.get("FIDELIZABOT_DB")
    if env_path:
        try:
            db_dir = os.path.dirname(env_path) or "."
            os.makedirs(db_dir, exist_ok=True)
            # Probar escritura
            with open(os.path.join(db_dir, ".wtest"), "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(os.path.join(db_dir, ".wtest"))
            return env_path
        except Exception:
            print("[WARN] FIDELIZABOT_DB apunta a una ruta no escribible. Intentando otras rutas...", file=sys.stderr)

    # B) ./data dentro del proyecto
    project_dir = os.path.abspath(os.path.dirname(__file__)) if "__file__" in globals() else os.getcwd()
    candidate = os.path.join(project_dir, "data")
    if _is_writable_dir(candidate):
        return os.path.join(candidate, filename)

    # C) Carpeta de datos del usuario
    udir = _user_data_dir()
    if _is_writable_dir(udir):
        return os.path.join(udir, filename)

    # D) CWD
    if _is_writable_dir(os.getcwd()):
        return os.path.join(os.getcwd(), filename)

    # E) Fallback memoria (no persistente; extremadamente raro)
    print("[WARN] No se encontró ninguna carpeta escribible. Usando DB en memoria (no persistente).", file=sys.stderr)
    return ":memory:"

DB_PATH = resolve_db_path()

def get_conn() -> sqlite3.Connection:
    """Abre una conexión SQLite con row_factory para acceder a columnas por nombre."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(seed: bool = True) -> None:
    """Crea tablas si no existen y hace seeding de recompensas."""
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                email TEXT UNIQUE,
                puntos INTEGER NOT NULL DEFAULT 0,
                nivel TEXT NOT NULL CHECK(nivel IN ('BRONCE','PLATA','ORO')),
                fecha_registro TEXT NOT NULL
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS transacciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                monto_cop INTEGER NOT NULL,
                tarjeta_aliada INTEGER NOT NULL DEFAULT 0,
                puntos_ganados INTEGER NOT NULL DEFAULT 0,
                puntos_redimidos INTEGER NOT NULL DEFAULT 0,
                descripcion TEXT,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS recompensas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                costo_puntos INTEGER NOT NULL,
                descripcion TEXT
            );
        """)

        if seed:
            cur.execute("SELECT COUNT(*) AS c FROM recompensas;")
            if int(cur.fetchone()["c"]) == 0:
                cur.executemany(
                    "INSERT INTO recompensas (nombre, costo_puntos, descripcion) VALUES (?, ?, ?);",
                    [
                        ("Café pequeño", 120, "Café filtrado tamaño pequeño."),
                        ("Capuchino mediano", 250, "Capuchino en vaso mediano."),
                        ("Sandwich del día", 400, "Sandwich simple de la casa."),
                        ("Combo café + postre", 550, "Café y postre a elección."),
                        ("Merch oficial", 900, "Taza/termo/bolsa de la marca."),
                    ],
                )
        conn.commit()

# =====================
#  Dominio (POO)
# =====================

@dataclass
class Cliente:
    """Clase base con lógica común. Subclases ajustan el multiplicador de tier."""
    id: Optional[int]
    nombre: str
    email: Optional[str]
    puntos: int
    nivel: str    # 'BRONCE' | 'PLATA' | 'ORO'
    fecha_registro: str

    BASE_POR_MIL: int = 1
    MULTIPLICADOR_TARJETA: float = 2.0
    UMBRAL_PLATA: int = 500
    UMBRAL_ORO: int = 1500

    def calcular_puntos(self, monto_cop: int, tarjeta_aliada: bool) -> int:
        """Regla base + multiplicadores de tier y tarjeta aliada (polimórfico)."""
        if monto_cop <= 0:
            return 0
        base = (monto_cop // 1000) * self.BASE_POR_MIL
        mult = self._multiplicador_tier()
        if tarjeta_aliada:
            mult *= self.MULTIPLICADOR_TARJETA
        return int(base * mult)

    def _multiplicador_tier(self) -> float:
        """Ganancia extra por tier (subclases redefinen)."""
        return 1.0

    def aplicar_upgrade_si_corresponde(self) -> str:
        """Devuelve el nivel que corresponde según puntos acumulados."""
        if self.puntos >= self.UMBRAL_ORO:
            return "ORO"
        if self.puntos >= self.UMBRAL_PLATA:
            return "PLATA"
        return "BRONCE"

    def beneficios(self) -> List[str]:
        return [
            "1 punto por cada $1.000 COP.",
            "Duplica puntos pagando con tarjeta aliada (convenios).",
        ]

class ClienteBronce(Cliente):
    def _multiplicador_tier(self) -> float:
        return 1.0
    def beneficios(self) -> List[str]:
        return super().beneficios() + ["Nivel Bronce: tasa base."]

class ClientePlata(Cliente):
    def _multiplicador_tier(self) -> float:
        return 1.25
    def beneficios(self) -> List[str]:
        return super().beneficios() + ["Nivel Plata: +25% puntos."]

class ClienteOro(Cliente):
    def _multiplicador_tier(self) -> float:
        return 1.5
    def beneficios(self) -> List[str]:
        return super().beneficios() + ["Nivel Oro: +50% puntos y prioridad."]

NIVEL_A_CLASE: dict[str, Type[Cliente]] = {
    "BRONCE": ClienteBronce,
    "PLATA": ClientePlata,
    "ORO": ClienteOro,
}

def cliente_from_row(row: sqlite3.Row) -> Cliente:
    """Instancia la subclase adecuada según 'nivel'."""
    cls = NIVEL_A_CLASE.get(row["nivel"], ClienteBronce)
    return cls(
        id=row["id"],
        nombre=row["nombre"],
        email=row["email"],
        puntos=row["puntos"],
        nivel=row["nivel"],
        fecha_registro=row["fecha_registro"],
    )

# =====================
#  Repositorios simples
# =====================

class ClienteRepo:
    @staticmethod
    def crear(nombre: str, email: Optional[str]) -> Cliente:
        fecha = datetime.now().isoformat(timespec="seconds")
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO clientes (nombre, email, puntos, nivel, fecha_registro) VALUES (?, ?, 0, 'BRONCE', ?);",
                (nombre.strip(), email, fecha),
            )
            new_id = cur.lastrowid
            cur.execute("SELECT * FROM clientes WHERE id = ?;", (new_id,))
            return cliente_from_row(cur.fetchone())

    @staticmethod
    def obtener(cliente_id: int) -> Optional[Cliente]:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM clientes WHERE id = ?;", (cliente_id,))
            row = cur.fetchone()
            return cliente_from_row(row) if row else None

    @staticmethod
    def actualizar(cliente_id: int, puntos: int, nivel: str) -> None:
        with get_conn() as conn:
            conn.execute("UPDATE clientes SET puntos = ?, nivel = ? WHERE id = ?;", (puntos, nivel, cliente_id))

class TransaccionRepo:
    @staticmethod
    def registrar(cliente_id: int, monto_cop: int, tarjeta_aliada: bool, puntos_g: int, puntos_r: int, desc: str) -> None:
        fecha = datetime.now().isoformat(timespec="seconds")
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO transacciones (cliente_id, fecha, monto_cop, tarjeta_aliada, puntos_ganados, puntos_redimidos, descripcion)
                   VALUES (?, ?, ?, ?, ?, ?, ?);""",
                (cliente_id, fecha, monto_cop, int(tarjeta_aliada), puntos_g, puntos_r, desc),
            )

    @staticmethod
    def historial(cliente_id: int) -> List[sqlite3.Row]:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM transacciones WHERE cliente_id = ? ORDER BY id DESC;", (cliente_id,))
            return cur.fetchall()

class RecompensaRepo:
    @staticmethod
    def listar() -> List[sqlite3.Row]:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM recompensas ORDER BY costo_puntos ASC;")
            return cur.fetchall()

    @staticmethod
    def obtener(recompensa_id: int) -> Optional[sqlite3.Row]:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM recompensas WHERE id = ?;", (recompensa_id,))
            return cur.fetchone()

# =====================
#  Servicio de aplicación
# =====================

class LoyaltyEngine:
    """Casos de uso: alta, compra, redención, consulta."""

    def registrar_cliente(self, nombre: str, email: Optional[str]) -> Cliente:
        if not nombre or not nombre.strip():
            raise ValueError("El nombre es obligatorio.")
        return ClienteRepo.crear(nombre, email or None)

    def registrar_compra(self, cliente_id: int, monto_cop: int, tarjeta_aliada: bool, descripcion: Optional[str]=None) -> Tuple[Cliente, int]:
        c = ClienteRepo.obtener(cliente_id)
        if not c:
            raise ValueError("Cliente no encontrado.")
        if monto_cop <= 0:
            raise ValueError("El monto debe ser positivo.")

        # Polimorfismo real: no nos importa si c es Bronce/Plata/Oro
        pts = c.calcular_puntos(monto_cop, tarjeta_aliada)
        TransaccionRepo.registrar(c.id, monto_cop, tarjeta_aliada, pts, 0, descripcion or "Compra en tienda")
        c.puntos += pts
        c.nivel = c.aplicar_upgrade_si_corresponde()
        ClienteRepo.actualizar(c.id, c.puntos, c.nivel)
        # Releemos por si cambió la clase efectiva (nivel -> subclase)
        return ClienteRepo.obtener(c.id), pts

    def redimir(self, cliente_id: int, recompensa_id: int) -> Tuple[Cliente, sqlite3.Row]:
        c = ClienteRepo.obtener(cliente_id)
        if not c:
            raise ValueError("Cliente no encontrado.")
        r = RecompensaRepo.obtener(recompensa_id)
        if not r:
            raise ValueError("Recompensa no encontrada.")
        costo = int(r["costo_puntos"])
        if c.puntos < costo:
            raise ValueError("Puntos insuficientes.")

        TransaccionRepo.registrar(c.id, 0, False, 0, costo, f"Redención: {r['nombre']}")
        c.puntos -= costo
        ClienteRepo.actualizar(c.id, c.puntos, c.nivel)  # en este modelo no hay downgrade
        return ClienteRepo.obtener(c.id), r

    def ver_cliente(self, cliente_id: int) -> Cliente:
        c = ClienteRepo.obtener(cliente_id)
        if not c:
            raise ValueError("Cliente no encontrado.")
        return c

    def listar_recompensas(self) -> List[sqlite3.Row]:
        return RecompensaRepo.listar()

    def historial(self, cliente_id: int) -> List[sqlite3.Row]:
        return TransaccionRepo.historial(cliente_id)

# =====================
#  CLI de demostración
# =====================

def print_cliente(c: Cliente) -> None:
    print(f"\n[Cliente #{c.id}] {c.nombre}")
    print(f"  Email: {c.email or '-'}")
    print(f"  Nivel: {c.nivel}")
    print(f"  Puntos: {c.puntos}")
    print("  Beneficios:")
    for b in c.beneficios():
        print(f"   - {b}")

def print_historial(rows: List[sqlite3.Row]) -> None:
    if not rows:
        print("  (sin transacciones)")
        return
    for r in rows:
        print(f"  #{r['id']} | {r['fecha']} | monto=${r['monto_cop']:,.0f} | tarjeta={'Sí' if r['tarjeta_aliada'] else 'No'} | +{r['puntos_ganados']} | -{r['puntos_redimidos']} | {r['descripcion'] or ''}")

def main():
    # Inicializamos la base donde corresponda. Si DB_PATH es ':memory:' lo avisamos.
    init_db(seed=True)
    if DB_PATH == ":memory:":
        print("[AVISO] La base corre en memoria (no persistirá). Establece FIDELIZABOT_DB o usa una carpeta escribible.", file=sys.stderr)

    engine = LoyaltyEngine()
    MENU = """
================== FIDELIZABOT (Demo CLI) ==================
1) Registrar cliente
2) Registrar compra
3) Redimir recompensa
4) Ver cliente
5) Ver historial de cliente
6) Listar recompensas
0) Salir
============================================================
Elige una opción: """

    while True:
        try:
            op = input(MENU).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSaliendo...")
            break

        try:
            if op == "1":
                nombre = input("Nombre: ").strip()
                email = (input("Email (opcional): ").strip() or None)
                c = engine.registrar_cliente(nombre, email)
                print_cliente(c)

            elif op == "2":
                cid = int(input("ID cliente: ").strip())
                monto = int(input("Monto COP: ").strip())
                tarjeta = input("Pagó con tarjeta aliada? (s/n): ").strip().lower() == "s"
                c, pts = engine.registrar_compra(cid, monto, tarjeta)
                print(f"\nCompra registrada. Puntos ganados: {pts}")
                print_cliente(c)

            elif op == "3":
                cid = int(input("ID cliente: ").strip())
                recs = engine.listar_recompensas()
                print("\nRecompensas:")
                for r in recs:
                    print(f"  {r['id']}) {r['nombre']} - {r['costo_puntos']} pts [{r['descripcion'] or ''}]")
                rid = int(input("ID recompensa: ").strip())
                c, r = engine.redimir(cid, rid)
                print(f"\nRedimiste: {r['nombre']} ({r['costo_puntos']} pts)")
                print_cliente(c)

            elif op == "4":
                cid = int(input("ID cliente: ").strip())
                c = engine.ver_cliente(cid)
                print_cliente(c)

            elif op == "5":
                cid = int(input("ID cliente: ").strip())
                rows = engine.historial(cid)
                print("\nHistorial:")
                print_historial(rows)

            elif op == "6":
                rows = engine.listar_recompensas()
                print("\nRecompensas:")
                for r in rows:
                    print(f"  {r['id']}) {r['nombre']} - {r['costo_puntos']} pts [{r['descripcion'] or ''}]")

            elif op == "0":
                print("¡Hasta luego!")
                break

            else:
                print("Opción no válida.")

        except Exception as e:
            # Mostramos el error de forma clara sin stack-trace (útil para demo de estudiantes).
            print(f"[Error] {e}")

if __name__ == "__main__":
    main()
