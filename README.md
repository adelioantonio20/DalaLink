# DalaLink — Plataforma de Mobilidade Urbana de Luanda

Infraestrutura digital de intermediação entre passageiros, taxistas, frotas e empresas em **Luanda, Angola** (`Africa/Luanda`, moeda **Kwanza — AOA**, idioma **Português**).

## Ambientes e Fases Implementadas (Fases 1 a 4)

1. **Aplicação do Passageiro (`PASSENGER`)** — Mobile-First PWA com mapa interativo de Luanda (OpenStreetMap/Leaflet), seleção de origem/destino, estimativa de tarifa em AOA, modo individual e **viagens em grupo** com validação individual de cartões QR, acompanhamento do veículo em tempo real, código PIN de embarque, cartão pré-pago digital (`MOB-000001` / `QR+NFC`), saldo no servidor, histórico de transações e avaliação da viagem.
2. **Aplicação do Motorista (`DRIVER`)** — Cockpit de alto contraste para baixa distração ao volante, com **alertas sonoros e voz em Português**, gestão de estado (`Disponível`, `Ocupado`, `Indisponível`), registo de veículos, aceitação/rejeição de solicitações com redistribuição automática, simulador/partilha GPS, **leitor QR + NFC Tap** com débito atómico, receitas/comissões e zonas de oportunidade.
3. **Portal Empresarial (`COMPANY_ADMIN` — Fase 2 Completa)** — Gestão de colaboradores e estados, rotas corporativas, **agendamentos recorrentes**, **agrupamento automático por destino e capacidade de viatura (ex.: 17h00)**, mapa ao vivo de viaturas corporativas, relatórios de custos por departamento/corredor e **exportação CSV**.
4. **Proprietário & Gestão de Frotas (`OWNER` — Fase 4)** — Rentabilidade por viatura (bruto, comissão e líquido), localização em tempo real da frota no mapa de Luanda, registo de novas viaturas e atribuição de motoristas.
5. **Painel Administrativo (`ADMIN` — Fases 1, 3 e 4)** — Torre de Controlo de Luanda com KPIs em tempo real, mapa operacional, **Inteligência de Mobilidade & Heatmap** (distribuição horária 24h, corredores O→D, congestionamento, espera média, recomendações de reposicionamento e indicador transparente de prontidão ML), validação documental de motoristas, gestão e emissão de cartões **QR/NFC**, filtros avançados por data/zona/estado, registo de adaptadores externos (Bilhética Angola / EMIS desativado até aprovação) e **Audit Logs** imutáveis.

## Contas de Demonstração (Password: `dalalink123`)

| Ambiente | Email | Detalhes de Teste |
| :--- | :--- | :--- |
| Passageiro | `passageiro@dalalink.ao` | Mateus Domingos • Cartão `MOB-000001` (`QR+NFC: NFC-AO-000001` • **10.000 AOA**) |
| Motorista 1 | `motorista@dalalink.ao` | Carlos Eduardo • **Hyundai i10** (`LD-42-18-AB`, 4 lug.) • Gamek |
| Motorista 2 | `motorista2@dalalink.ao` | Fernando Quiosa • **Toyota HiAce** (`LD-88-90-CD`, 12 lug.) • Maianga |
| Motorista 3 | `motorista3@dalalink.ao` | Miguel Teixeira • Kia Picanto (`PENDING` — testar aprovação Admin) |
| Empresa | `empresa@dalalink.ao` | Atlântico Energia & Serviços, Lda. • 5 colaboradores, rotas e recorrências (17:00) |
| Proprietário / Frota | `frota@dalalink.ao` | Frota DalaLink Luanda • Gestão e rentabilidade das 3 viaturas |
| Administração | `admin@dalalink.ao` | Torre de Controlo Operacional & Inteligência de Mobilidade Luanda |

Cartões adicionais pré-carregados para validação de segurança:
- `MOB-000002` (Ana Paula Costa — **5.000 AOA**, `ACTIVE`, ideal para testar viagem em grupo)
- `MOB-000003` (João Manuel — **400 AOA**, `ACTIVE`, testa recusa por **saldo insuficiente**)
- `MOB-000004` (Sara Baptista — **8.000 AOA**, `BLOCKED`, testa recusa de **cartão bloqueado**)

## Cenário Principal de Validação (Gamek → Aeroporto)

1. Entre como **Passageiro** (`passageiro@dalalink.ao`) e confirme o trajeto **Gamek → Aeroporto Internacional 4 de Fevereiro** (Tarifa: **1.000 AOA**).
2. Troque para **Motorista** (`motorista@dalalink.ao` — Hyundai i10), aceite a solicitação, avance a posição GPS e marque chegada.
3. Valide o cartão **`MOB-000001`** no leitor QR: o saldo passa atomicamente de **10.000 AOA → 9.000 AOA** (novas leituras duplicadas são bloqueadas).
4. Inicie e conclua a viagem no Aeroporto (comissão 15% = 150 AOA; líquido motorista = 850 AOA).
5. Abra o **Painel Administrativo** (`admin@dalalink.ao`) para confirmar receita, comissão, histórico da viagem e registos de auditoria.

## Execução Local

### Backend (FastAPI)
```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

### Testes Automatizados (Pytest)
```bash
cd backend
PYTHONPATH=. .venv/bin/pytest -v
```

### Frontend (React + TypeScript + Tailwind + PWA)
```bash
cd frontend
npm install
npm run dev
```

### Stack Completa com PostgreSQL + PostGIS (Docker)
```bash
docker compose up --build
```

## Notas de Produção (Angola / Luanda)
- **Mapas (OSM/Leaflet):** gratuito em desenvolvimento e testes; em produção comercial deve utilizar-se servidor próprio de tiles ou fornecedor dedicado conforme a política de uso do OpenStreetMap.
- **Pagamentos & Bilhética:** nesta Fase 1 utiliza-se exclusivamente carregamento administrativo e saldo no servidor (`wallets`). A arquitetura suporta evolução para NFC (`nfc_uid`) e integração futura autorizada com prestadores locais.
- **Notificações:** WebSockets e Web Audio/Speech gratuitos no MVP; SMS em Angola exigirá gateway aprovado em produção.
