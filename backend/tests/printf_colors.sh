#!/bin/bash

# Script para probar colores con printf vs echo -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Símbolos
CHECK="✅"
CROSS="❌"
WARNING="⚠️"

echo "=== PRUEBA DE COLORES ==="
echo

echo "1. Con printf:"
printf "${RED}Texto rojo${NC}\n"
printf "${GREEN}Texto verde${NC}\n" 
printf "${BLUE}Texto azul${NC}\n"
printf "${YELLOW}Texto amarillo${NC}\n"
printf "${CYAN}Texto cyan${NC}\n"

echo
echo "2. Con echo -e:"
echo -e "${RED}Texto rojo${NC}"
echo -e "${GREEN}Texto verde${NC}"
echo -e "${BLUE}Texto azul${NC}" 
echo -e "${YELLOW}Texto amarillo${NC}"
echo -e "${CYAN}Texto cyan${NC}"

echo
echo "3. Símbolos (printf):"
printf "%s Símbolo check\n" "$CHECK"
printf "%s Símbolo cross\n" "$CROSS"
printf "%s Símbolo warning\n" "$WARNING"

echo
echo "4. Símbolos (echo):"
echo "$CHECK Símbolo check"
echo "$CROSS Símbolo cross" 
echo "$WARNING Símbolo warning"

echo
echo "5. Combinado printf:"
printf "${GREEN}%s printf verde${NC}\n" "$CHECK"
printf "${RED}%s printf rojo${NC}\n" "$CROSS"

echo
echo "6. Combinado echo -e:"
echo -e "${GREEN}$CHECK echo verde${NC}"
echo -e "${RED}$CROSS echo rojo${NC}"

echo
echo "=== FIN PRUEBA ==="