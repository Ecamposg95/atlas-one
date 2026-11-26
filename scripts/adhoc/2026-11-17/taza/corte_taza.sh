#!/usr/bin/env bash
# Corte de El Mundo de la Taza Toluca (rmazh suc 18) -> Atlas ONE org 21. NO correr sin el visto bueno.
# Paso a paso: bash corte_taza.sh 1 | 2 | 3 | 4 | 5
set -euo pipefail
S=/tmp/claude-1000/-mnt-d-Devs-atlas-one/303e01a5-a551-4749-9640-4f8a0f3bbd85/scratchpad/taza
W=/mnt/d/Devs/atlas-one/.worktrees/taza
RMAZH=/mnt/d/Devs/Atlas-Rmazh
SSH_RW="railway ssh -i ~/.ssh/id_ed25519_railway -s Atlas-API --"
case "${1:-}" in
  1) # Cajas cerradas + apagar a Fernanda, Ximena y America en rmazh (rmazh rechaza tokens de inactivos)
     cd $RMAZH
     $SSH_RW 'cd /app && /opt/venv/bin/python - ' < $S/apagar_taza_rmazh.py
     read -p "¿Ninguna caja abierta (o se aceptan abiertas)? ENTER apaga, Ctrl-C cancela "
     $SSH_RW 'cd /app && /opt/venv/bin/python - --ejecutar' < $S/apagar_taza_rmazh.py ;;
  2) # Exportar DESPUES de apagarlas (solo lectura; trae hashes, se queda en el scratchpad)
     cd $RMAZH
     $SSH_RW 'cd /app && /opt/venv/bin/python - 5' < $W/scripts/export_rmazh_org.py > $S/org5_corte.txt
     grep CONTEO $S/org5_corte.txt ;;
  3) # Respaldo + ensayo en prod (escribe y deshace)
     scp -q $W/scripts/import_rmazh_org.py $S/org5_corte.txt ionos:/root/
     ssh ionos 'set -e; f=/srv/backups/atlas_one_prod_antes_de_la_taza_$(date +%Y%m%d_%H%M).sql.gz;
       docker exec postgres pg_dump -U postgres atlas_one_prod | gzip > $f; ls -la $f;
       docker exec atlas-one-prod mkdir -p /tmp/taza;
       docker cp /root/import_rmazh_org.py atlas-one-prod:/tmp/taza/; docker cp /root/org5_corte.txt atlas-one-prod:/tmp/taza/;
       rm /root/import_rmazh_org.py /root/org5_corte.txt;
       docker exec -w /app -e PYTHONPATH=/app atlas-one-prod python /tmp/taza/import_rmazh_org.py /tmp/taza/org5_corte.txt --org-destino 21 --sucursales 18' ;;
  4) # Real. Si quedo una caja abierta, agregar: --permitir-cajas-abiertas --rmazh-apagado
     ssh ionos 'docker exec -w /app -e PYTHONPATH=/app atlas-one-prod python /tmp/taza/import_rmazh_org.py /tmp/taza/org5_corte.txt --org-destino 21 --sucursales 18 --ejecutar' ;;
  5) # Reactivar a Fernanda y Ximena en Atlas ONE (llegan inactivas) y verificar; borrar la exportacion del contenedor
     ssh ionos "docker exec -i postgres psql -U postgres -d atlas_one_prod -c \"update users set is_active = true where id in (55, 56) returning id, username, is_active, branch_id;\" -c \"select id, name, can_sell, printer_name from branches where organization_id = 21;\"; docker exec atlas-one-prod rm -rf /tmp/taza" ;;
  *) echo "uso: bash corte_taza.sh 1|2|3|4|5"; exit 1 ;;
esac
