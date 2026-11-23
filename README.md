# DalaLink v2.0 — Inteligência e Intermediação de Informação de Mobilidade Urbana (Luanda)

Plataforma tecnológica focada em resolver a falta de informação sobre **procura de passageiros** e **disponibilidade de táxis** nas diferentes vias e paragens de **Luanda, Angola** (`Africa/Luanda`, idioma Português).

- **Para passageiros:** *"Saiba como está a sua via antes de sair de casa."*
- **Para motoristas:** *"Saiba onde existe procura antes de escolher a sua próxima via."*

> **Âmbito do MVP v2.0 (Secções 3 e 14):** Funcionalidades financeiras (carteiras digitais, saldos, cartões pré-pagos, QR financeiro, cobranças, comissões, pagamentos bancários e gestão financeira de frotas) foram **desactivadas da experiência MVP** (`ENABLE_LEGACY_FINANCE_MODULES=False`), preservando o código e tabelas no repositório para eventual evolução futura.

## Ambientes Activos

1. **Ambiente do Passageiro (`passageiro@dalalink.ao`):**
   - Consulta de disponibilidade por origem e destino (ex.: **Gamek → Maianga**), distinguindo **procura declarada** vs **confirmada** e **oferta declarada** vs **observada em campo**.
   - Comparação com paragens alternativas próximas (ex.: **Rocha Gamek → Maianga**), hora da última actualização, aviso de dados desactualizados (`STALE`) e mensagem explícita **`"Informação insuficiente para esta via."`** quando não existem registos válidos (ex.: **Viana → Kilamba**).
   - Declaração de intenção de viajar (com anti-duplicação), confirmação física de presença na paragem e cancelamento.
   - Mapa interactivo de Luanda (OpenStreetMap + Leaflet) com dados exclusivamente agregados (privacidade de localização).
2. **Ambiente do Motorista (`motorista@dalalink.ao`):**
   - Aviso permanente de segurança rodoviária (*"Consulte apenas com o veículo imobilizado"*).
   - Ranking de vias por procura estimada com linguagem cautelosa (*"Procura estimada elevada"*, *"Possível oportunidade de procura"*), destinos mais procurados, horários de ponta e mapa de calor.
   - Declaração de disponibilidade por via/paragem com expiração automática e deduplicação por motorista.
3. **Recolha de Campo & Painel Administrativo (`campo@dalalink.ao` e `admin@dalalink.ao`):**
   - Gestão geográfica completa: Municípios → Bairros → Zonas → Paragens Validadas → Vias → Destinos.
   - Registo presencial de observações de campo (táxis observados, passageiros à espera, tempo estimado, condição da via) e fila de validação administrativa.
   - Controlo de qualidade (% dados validados, % desactualizados/expirados, sinalização de suspeitos).
   - Relatórios históricos descritivos (município, bairro, paragem, destino, dia da semana e hora) e **limites configuráveis** de classificação e expiração.

## Contas de Demonstração (Password: `dalalink123`)

| Perfil | Email | Descrição |
| :--- | :--- | :--- |
| Passageiro | `passageiro@dalalink.ao` | Mateus Domingos |
| Motorista | `motorista@dalalink.ao` | Carlos Eduardo |
| Recolha de Campo | `campo@dalalink.ao` | Nelson Quissanga |
| Administração | `admin@dalalink.ao` | Adélio António |

## Execução Local e Testes

### Backend (FastAPI + 22 Entidades de Mobilidade)
```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

### Suite de Testes Automatizados (12 cenários de validação)
```bash
cd backend
PYTHONPATH=. .venv/bin/pytest -v tests/test_mobility_info_mvp.py
```

### Frontend Web (React + TypeScript + Tailwind + Leaflet + PWA)
```bash
cd frontend
npm install
npm run dev
```

### Compilação do APK Android (`DalaLink-Luanda-v2.0.apk`)
```bash
bash android/build_apk.sh
```
