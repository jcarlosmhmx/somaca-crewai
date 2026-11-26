"""Toma capturas de la GUI con Playwright durante una corrida real (para el README y la presentación).

Requiere la API (puerto 8000) y Streamlit (puerto 8501) corriendo:
    python scripts/capturas.py            # corrida en vivo con el LLM de .env
    python scripts/capturas.py --replay   # modo respaldo (sin LLM)
    python scripts/capturas.py --existente  # sin nueva corrida: usa la última ya completada
Guarda los PNG en docs/capturas/.
"""
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

DESTINO = Path(__file__).resolve().parents[1] / "docs" / "capturas"
DESTINO.mkdir(parents=True, exist_ok=True)
UI = os.getenv("SOMACA_UI", "http://localhost:8501")
API = os.getenv("SOMACA_API", "http://localhost:8000")
REPLAY = "--replay" in sys.argv
EXISTENTE = "--existente" in sys.argv


def paso(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def esperar_quieto(page, s=2.5):
    page.wait_for_timeout(int(s * 1000))


def foto(page, nombre):
    ruta = DESTINO / f"{nombre}.png"
    page.screenshot(path=str(ruta))
    paso(f"captura {ruta.name}")


def pestana(page, texto):
    page.get_by_role("tab", name=texto).click()
    esperar_quieto(page, 1.5)


def capturar_existente(page):
    """Capturas de la última corrida completada, sin lanzar otra (no gasta en el LLM)."""
    # Flujo completado (la barra lateral ya selecciona la corrida más reciente)
    pestana(page, "🤖 Flujo de agentes")
    esperar_quieto(page, 3)
    foto(page, "02_flujo_completado")

    # Auditoría: veredicto, recomendación, delegación del Broker y tabla PEAS
    pestana(page, "🧾 Auditoría y decisión")
    page.set_viewport_size({"width": 1600, "height": 1500})
    esperar_quieto(page, 3)
    foto(page, "03_auditoria_veredicto")
    page.get_by_text("Justificación del Broker y aclaraciones (delegación)").click()
    esperar_quieto(page, 1.5)
    page.set_viewport_size({"width": 1600, "height": 2800})
    esperar_quieto(page, 2)
    foto(page, "04_auditoria_delegacion_y_peas")

    # Human-in-the-Loop 1: ajuste inválido (Cultural 350 MXN, fuera de ±20 %)
    page.get_by_text("✏️ Ajustar montos").click()
    esperar_quieto(page, 3)
    control = page.get_by_role("slider").first
    control.focus()
    for _ in range(20):  # 250 → 350 MXN en pasos de 5
        control.press("ArrowRight")
        page.wait_for_timeout(80)
    esperar_quieto(page, 4)
    foto(page, "05_alerta_ajuste_invalido")

    # Human-in-the-Loop 2: aprobar con observaciones y registrar
    page.get_by_text("✅ Aprobar recomendación").click()
    esperar_quieto(page, 3)
    page.get_by_label("Responsable").fill("Juan Carlos Morales Herrera")
    page.get_by_label("Responsable").press("Tab")
    esperar_quieto(page)
    caja = page.get_by_text("Revisé las observaciones del Monitor")
    if caja.count():
        caja.click()
        esperar_quieto(page)
    comentario = page.get_by_label("Comentario (obligatorio salvo aprobación limpia)")
    comentario.fill("Revisé CPL y leads fuera de meta; apruebo 250/250 y monitoreamos Cultural en el segmento 1.")
    comentario.press("Tab")
    esperar_quieto(page)
    foto(page, "06_decision_humana")
    page.get_by_role("button", name="Registrar decisión").click()
    esperar_quieto(page, 5)
    pestana(page, "🧾 Auditoría y decisión")
    foto(page, "07_decision_registrada")

    page.set_viewport_size({"width": 1600, "height": 1000})
    pestana(page, "🗂️ Historial")
    foto(page, "08_historial")


if EXISTENTE:  # quitar capturas de corridas anteriores para no mezclar
    for viejo in DESTINO.glob("*.png"):
        viejo.unlink()

with sync_playwright() as p:
    nav = p.chromium.launch()
    page = nav.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)

    # 0. Documentación OpenAPI de la API
    page.goto(f"{API}/docs")
    page.get_by_text("SOMACA API").first.wait_for(timeout=30000)  # que sea la API correcta
    esperar_quieto(page, 3)
    foto(page, "00_api_openapi")

    # 1. Resumen
    page.set_viewport_size({"width": 1600, "height": 1500})
    page.goto(UI)
    page.get_by_text("Reparto del presupuesto de Meta Ads").wait_for(timeout=60000)
    esperar_quieto(page, 4)
    foto(page, "01_resumen")

    if EXISTENTE:
        capturar_existente(page)
        nav.close()
        paso(f"listo: {DESTINO}")
        sys.exit(0)

    # 2. Lanzar la corrida y capturar el monitor en vivo
    if REPLAY:
        page.get_by_text("Respaldo grabado (Fase 3)").click()
        esperar_quieto(page)
    pestana(page, "🤖 Flujo de agentes")
    page.get_by_role("button", name="▶ Ejecutar SOMACA").click()
    paso("corrida iniciada")
    esperar_quieto(page, 5)
    pestana(page, "🤖 Flujo de agentes")
    t0 = time.time()
    capturas_vivo = 0
    while time.time() - t0 < 900:
        if page.get_by_text("Corrida completada").count() or page.get_by_text("Corrida fallida").count():
            break
        if capturas_vivo < 3 and time.time() - t0 > 20 + capturas_vivo * 40:
            foto(page, f"02_flujo_en_vivo_{capturas_vivo + 1}")
            capturas_vivo += 1
        page.wait_for_timeout(3000)
    paso(f"corrida terminada en {time.time() - t0:.0f} s")
    esperar_quieto(page, 6)
    pestana(page, "🤖 Flujo de agentes")
    foto(page, "03_flujo_completado")

    # 3. Auditoría
    pestana(page, "🧾 Auditoría y decisión")
    esperar_quieto(page, 3)
    page.set_viewport_size({"width": 1600, "height": 2600})
    esperar_quieto(page, 2)
    foto(page, "04_auditoria")

    # 4. Human-in-the-Loop: ajuste inválido → aviso; luego aprobación con observaciones
    try:
        page.get_by_text("✅ Aprobar recomendación").click()
        esperar_quieto(page)
        page.get_by_label("Responsable").fill("Juan Carlos Morales")
        page.get_by_label("Responsable").press("Tab")
        esperar_quieto(page)
        caja = page.get_by_text("Revisé las observaciones del Monitor")
        if caja.count():
            caja.click()
            esperar_quieto(page)
        page.get_by_label("Comentario (obligatorio salvo aprobación limpia)").fill(
            "Revisé CPL y leads fuera de meta; apruebo el reparto y monitoreamos el segmento 5.")
        page.get_by_label("Comentario (obligatorio salvo aprobación limpia)").press("Tab")
        esperar_quieto(page)
        foto(page, "05_decision_humana")
        page.get_by_role("button", name="Registrar decisión").click()
        esperar_quieto(page, 5)
        pestana(page, "🧾 Auditoría y decisión")
        foto(page, "06_decision_registrada")
    except Exception as e:  # noqa: BLE001
        paso(f"no se pudo completar la decisión automática: {e}")

    # 5. Historial
    page.set_viewport_size({"width": 1600, "height": 1000})
    pestana(page, "🗂️ Historial")
    foto(page, "07_historial")
    nav.close()
paso(f"listo: {DESTINO}")
