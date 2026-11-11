"""Resume el registro de consumo de la laptop (registro_consumo/consumo.csv) por día y por mes.

Uso (desde tesis-backend):  python scripts/resumen_consumo.py

Para cada día y cada mes muestra las horas encendido, la energía (kWh), la potencia promedio (W)
y las emisiones (kg CO2e) con el factor de la red peruana que usa CodeCarbon. Sirve para el
seguimiento del consumo en el tiempo que pide el anexo de software verde.
"""
import csv
import os
import sys
from collections import defaultdict

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(RAIZ, "registro_consumo", "consumo.csv")


def main():
    if not os.path.isfile(CSV):
        sys.exit(f"Todavía no hay registro: {CSV} (se crea al encender el backend local).")
    dias = defaultdict(lambda: [0.0, 0.0, 0.0])      # horas, kWh, kg CO2e
    with open(CSV, encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            dia = fila["timestamp"][:10]
            dias[dia][0] += float(fila["duration"]) / 3600
            dias[dia][1] += float(fila["energy_consumed"])
            dias[dia][2] += float(fila["emissions"])
    meses = defaultdict(lambda: [0.0, 0.0, 0.0])
    for dia, v in dias.items():
        for i in range(3):
            meses[dia[:7]][i] += v[i]

    def tabla(titulo, datos):
        print(f"\n{titulo}")
        print(f"{'Periodo':<12}{'Horas':>8}{'kWh':>10}{'W prom.':>10}{'kg CO2e':>10}")
        for k in sorted(datos):
            h, kwh, co2 = datos[k]
            w = kwh / h * 1000 if h else 0
            print(f"{k:<12}{h:>8.1f}{kwh:>10.3f}{w:>10.1f}{co2:>10.3f}")

    tabla("Por día", dias)
    tabla("Por mes", meses)


if __name__ == "__main__":
    main()
