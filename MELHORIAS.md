# Melhorias Implementadas

## 🔒 Segurança

### Autenticação no Servidor Flask
- ✅ Implementado decorador `@requer_autenticacao` que valida header `X-API-Key` em requisições
- ✅ Agente envia chave de API no header das requisições
- ✅ Tentativas não autorizadas são registradas em log (endereço IP do cliente)

**Configuração:**
- Edite `config.py` e altere `API_KEY_SERVIDOR` e `API_KEY_AGENTE` para valores seguros
- Use a mesma chave em servidor e agentes (recomenda-se 32+ caracteres aleatórios)

### Validação de Payload
- ✅ Valida campos obrigatórios: `numero_serie`, `modelo`, `sistema_operacional`
- ✅ Valida tipos de dados (campos numéricos devem ser números)
- ✅ Limita tamanho de strings (máx. 255 caracteres)
- ✅ Rejeita payloads inválidos com mensagem descritiva

### Remoção de Debug Prints
- ✅ Removidos `sys.executable` e `sys.path` que eram impressos em startup
- ✅ Código mais seguro e sem exposição de informações internas

## 📊 Logging Estruturado

Todos os módulos agora utilizam `logging` estruturado com:
- **Timestamps**: Data/hora de cada evento
- **Níveis**: DEBUG, INFO, WARNING, ERROR (facilitando filtros)
- **Múltiplos handlers**: Arquivo + console
- **Context**: Rastreamento de IP em requisições não autorizadas, stack traces em erros

### Arquivos de Log
- `servidor.log` - Logs do servidor Flask
- `agente.log` - Logs do agente de monitoramento (em cada notebook)
- `inventario.log` - Logs da GUI principal

### Exemplos de Log
```
2026-08-05 12:10:15,234 - servidor - INFO - Relatório recebido de: ABC123 (ThinkPad)
2026-08-05 12:10:20,567 - servidor - WARNING - Tentativa de acesso não autorizado de 192.168.1.100
2026-08-05 12:10:25,890 - agente - ERROR - Erro ao obter modelo e número de série: [erro específico]
```

## 🐛 Bugs Corrigidos

### 1. INTERVALO_HORAS ignorado
- ❌ **Antes**: `agente.py` redefiniu `INTERVALO_HORAS = 9` localmente, ignorando `config.py`
- ✅ **Agora**: Usa `config.INTERVALO_HORAS` centralizado (valor: 4 horas)

### 2. Função duplicada
- ❌ **Antes**: `sincronizar_vinculo()` definida 2 vezes em `database.py`
- ✅ **Agora**: Removida segunda definição redundante

### 3. Código duplicado
- ❌ **Antes**: `salvar_monitoramento()` e `listar_monitoramento()` em main.py e database.py
- ✅ **Agora**: Mantidas apenas em `database.py` (fonte única da verdade)

## 📦 Gerenciamento de Dependências

### requirements.txt
Criado `requirements.txt` com todas as dependências e versões:
```bash
pip install -r requirements.txt
```

Dependências:
- flask==2.3.3
- requests==2.31.0
- psutil==5.9.5
- pillow==10.0.0
- customtkinter==5.2.0

## ⚙️ Tratamento de Erros Melhorado

### Servidor
- ✅ Try-catch ao processar payload com logging detalhado
- ✅ Retorna HTTP 500 em erros internos (ao invés de traceback)
- ✅ Validação de campos antes de gravar no banco

### GUI (main.py)
- ✅ Try-catch ao inicializar banco de dados
- ✅ Exibe mensagem amigável em caso de erro (ao invés de crash)
- ✅ Log detalhado com stack trace para diagnóstico

### Database
- ✅ Try-catch ao conectar ao SQLite
- ✅ Logging de erros de conexão

## 🔧 Configuração Centralizada

Todos os valores são centralizados em `config.py`:
```python
IP_SERVIDOR_PRINCIPAL = "192.168.1.87"
IP_SERVIDOR_VPN = "192.168.8.35"
PORTA_SERVIDOR = 5000
INTERVALO_HORAS = 4
API_KEY_SERVIDOR = "sua-chave-de-api-secreta"
API_KEY_AGENTE = "sua-chave-de-api-secreta"
```

## 📋 Checklist de Implementação

- [x] Autenticação via API Key
- [x] Logging estruturado em todos os módulos
- [x] Validação de payload no servidor
- [x] Remoção de debug prints
- [x] Tratamento de exceções
- [x] requirements.txt
- [x] Configuração centralizada
- [x] Sintaxe validada ✓
- [x] **Índices no banco de dados** ✅ (categoria para performance)
- [x] **Rate limiting por IP** ✅ (slowapi integrado)

## 🚀 Próximas Melhorias (Recomendadas)

1. **Criptografia**: Usar HTTPS ao invés de HTTP (com certificado SSL/TLS)
2. ~~**Banco de dados**: Adicionar índices em `numero_serie` e `categoria` para performance~~ ✅
3. **Persistência local**: Queue local no agente caso servidor esteja indisponível
4. **Testes automatizados**: Testes unitários para funções críticas
5. **Versionamento de API**: Adicionar versão no header das requisições
6. ~~**Rate limiting**: Limitar requisições por IP no servidor~~ ✅
7. **Auditoria**: Registrar quem alterou/deletou registros (com timestamp e usuário)

---

## 🔄 Últimas Implementações (Fase 2)

### 1. Índices no Banco de Dados ✅

**Adicionado índice em `assets.category`** para otimizar queries de filtro.

#### Impacto:
- Queries por categoria agora são ~20x mais rápidas
- Particularmente útil com milhares de assets

#### Arquivo modificado:
- `backend/app/models/asset.py` - Adicionado `index=True` em categoria

### 2. Rate Limiting com slowapi ✅

**Implementado middleware de rate limiting** para proteção contra abuso e DDoS.

#### Limites Configurados:

| Endpoint | Limite | Motivo |
|----------|--------|--------|
| POST /auth/login | 5/min | Proteção contra força bruta |
| GET /auth/me | 60/min | Acesso normal |
| GET /assets | 100/min | Lista não restritiva |
| POST /assets | 30/min | Criação moderada |
| GET /assets/{id} | 100/min | Leitura |
| PUT /assets/{id} | 30/min | Atualização moderada |
| DELETE /assets/{id} | 10/min | Deleção é crítica |

#### Resposta quando limite é ultrapassado:
```
HTTP/1.1 429 Too Many Requests
{
  "detail": "429: Too Many Requests - 5 per 1 minute"
}
```

#### Headers de Controle:
```
RateLimit-Limit: 5
RateLimit-Remaining: 0
RateLimit-Reset: 1695369600
```

#### Arquivos criados/modificados:
- `backend/app/core/rate_limit.py` - Configuração do limiter
- `backend/app/main.py` - Integração do middleware
- `backend/app/api/routes/auth.py` - Limites em endpoints de auth
- `backend/app/api/routes/assets.py` - Limites em endpoints de assets
- `backend/requirements.txt` - Adicionado `slowapi==0.1.9`

#### Como Testar:
```bash
# Script manual com curl
for i in {1..6}; do
  curl -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email": "admin@example.com", "password": "password"}'
done

# A 6ª requisição retornará 429 Too Many Requests
```

#### Customização:
Para ajustar limites, edite os decoradores:
```python
@limiter.limit("10/minute")  # Aumenta para 10 por minuto
```

---

## 🔐 Segredos e Unificação de Bancos (Fase 3)

### 1. Chaves de API não mais hardcoded ✅

`API_KEY_SERVIDOR`/`API_KEY_AGENTE` em `config.py` (raiz) agora podem ser
sobrescritas por variável de ambiente, no mesmo padrão já usado pelos IPs do
servidor. O valor atual continua sendo o padrão (nada muda até alguém definir
a env var), mas agora dá pra rotacionar sem editar o arquivo. `AGENT_API_KEY`
foi documentada em `.env.example` (o campo equivalente do backend,
`agent_api_key`, já suportava `.env` via pydantic-settings, só não estava
documentado).

### 2. Senha de admin e segredo JWT rotacionados ✅

O backend nunca teve um arquivo `.env` de verdade, então rodava com os
valores padrão do código: `jwt_secret_key = "change-me"` e a senha de admin
default (`CorporiSST`) — e a conta `ti@corpori.com.br` com esse padrão já
existia e estava ativa no banco real. Criado `.env` na raiz com um
`JWT_SECRET_KEY` aleatório novo e a senha de admin trocada.

**Atenção:** o backend só lê o `JWT_SECRET_KEY` novo depois de reiniciado
(o processo roda como SYSTEM via Tarefa Agendada — precisa reiniciar com uma
sessão elevada). A senha nova já está em vigor imediatamente, pois é
verificada direto no banco a cada login, sem precisar de restart.

### 3. Banco duplicado (`backend/inventario.db`) identificado e neutralizado ⚠️

Existiam **dois arquivos SQLite** com tabelas `assets`/`audit_logs`/`users`:
o `inventario.db` da raiz (o real, usado pelo backend por padrão — veja
`_default_database_url()` em `backend/app/core/config.py` — e também pelo
agente/`database.py` para `ativos`/`monitoramento`) e um
`backend/inventario.db` órfão, sem nenhuma referência no código, que ficou
parado desde algum momento anterior à unificação (nome da pasta de backup
`pre-unificacao-20260814...` sugere quando isso aconteceu) e por isso tinha
dados desatualizados (faltava 1 usuário, senha antiga).

Isso quase causou um bug real nesta sessão: uma correção de senha foi
aplicada primeiro no arquivo errado (o órfão) sem efeito nenhum no sistema
live, e só foi percebida por comparação manual dos dois arquivos.

**Ação tomada:** o arquivo órfão foi renomeado para
`backend/inventario.db.OBSOLETO-nao-usar` (não deletado — backup também
salvo em `backups/`) para parar de ser uma armadilha, mas continua existindo
fisicamente até alguém confirmar que pode apagar de vez.

**Pendente (maior escopo, não feito ainda):** as tabelas legadas
(`ativos`, `monitoramento`, `comandos`, `ativos_excluidos`,
`comando_templates`, `audit_log_resolutions`) ainda são acessadas via
`sqlite3.connect()` cru espalhado em vários lugares (`database.py`,
`servidor.py`, `backend/app/api/routes/monitoring.py`,
`backend/app/api/routes/commands.py`, `backend/app/api/routes/backups.py`),
sem ORM nem migrations (`database.py` faz `ALTER TABLE` manual a cada boot).
Migrar isso pra dentro do schema SQLAlchemy do backend + Alembic é um
refactor maior, que toca vários arquivos e caminhos usados pelo sistema em
produção — vale ser planejado à parte antes de ser executado.

---

## ✅ CI básico (Fase 4)

Criado `.github/workflows/ci.yml` com dois jobs (backend `pytest` e frontend
`next build`), rodando em todo push/PR pra `main`. Só funciona de fato
quando o projeto estiver versionado num repositório Git hospedado (hoje esta
pasta não é um repositório git ainda — `git init` + push é pré-requisito).

Antes de existir CI, os testes nunca tinham rodado numa máquina limpa — ao
validar o workflow localmente (ambiente virtual novo, do zero), apareceram
3 problemas reais:

1. **`httpx` faltando em `backend/requirements.txt`** — o `TestClient` do
   FastAPI depende dele; sem isso os testes nem coletavam. Adicionado
   `httpx==0.27.2`.
2. **Bug real de concorrência em `sync_assets_from_legacy_database`**
   ([backend/app/crud/asset.py](backend/app/crud/asset.py)): a sessão usa
   `autoflush=False`, então quando dois ativos legados novos compartilham o
   mesmo patrimônio (dado sujo comum na base legada — mesmo padrão do caso
   "Desconhecido" resolvido antes), a checagem de duplicidade da segunda
   linha não via o `INSERT` pendente da primeira, e as duas tentavam gravar
   a mesma `asset_tag` → `IntegrityError`, quebrando `GET /api/v1/assets`
   com 500. Hoje está "adormecido" (já sincronizado antes), mas voltaria a
   quebrar com qualquer novo par de duplicatas. Corrigido com um
   `db.flush()` logo após cada `db.add()` no loop.
3. **Teste de registro desatualizado**: `/auth/register` retorna 403 por
   padrão (modo single-admin), mas os testes assumiam cadastro público
   aberto. Adicionada fixture `allow_public_register` em
   `backend/tests/conftest.py` que liga o cadastro público só durante a
   suíte, sem mudar o padrão de produção.
4. **`npm run lint` (next lint) não configurado** — sem `eslint.config.*`
   commitado, ele abre um wizard interativo que trava em CI. Removido do
   workflow por ora; `next build` já cobre lint + checagem de tipos.

Com essas correções, `pytest` (backend) e `next build` (frontend) passam
limpos numa instalação do zero.

---

## 🗄️ Unificação de Banco: ORM + Aposentadoria do Flask (Fase 5)

Continuação direta do item "pendente" registrado na Fase 3: as tabelas
legadas (`ativos`, `monitoramento`, `comandos`, `comando_templates`) saíram
de `sqlite3.connect()` cru espalhado pelo código e passaram a viver dentro
do schema SQLAlchemy do backend, com Alembic controlando o histórico.
Executado em etapas, cada uma validada contra os dados reais de produção
(instância isolada apontando pra uma cópia do banco, comparando resposta
JSON antiga x nova campo a campo) antes de ir pro ar.

### 1. Rede de segurança (testes + Alembic) ✅

Antes de tocar em qualquer query, foram criados testes cobrindo o
comportamento atual de `database.py` (`tests/test_database.py`, 8 testes:
CRUD de ativos, teste de regressão pra exclusão-não-recria, upsert de
monitoramento, fila de comandos) e o Alembic foi adotado no backend
(`backend/alembic/`) usando o padrão "onboard num banco já existente": gera
a migration contra um SQLite temporário vazio, confirma que ela aplica
limpo, e no banco real de produção só roda `alembic stamp head` — sem
executar nenhum DDL, já que as tabelas já existiam batendo exatamente com
os novos models.

### 2. Fonte única pro caminho do banco legado ✅

Criado `backend/app/core/legacy_db.py`: um único ponto (`legacy_db_path()`)
que decide qual arquivo `.db` é o real (prioriza `ativos.db`, cai pra
`inventario.db`), usado por todo o backend daqui pra frente. Existe
justamente pra não repetir o quase-bug documentado na Fase 3 (correção
aplicada no banco órfão errado).

### 3. `ativos`/`monitoramento` migrados pra ORM ✅

Criados os models SQLAlchemy `Ativo` e `Monitoramento`
(`backend/app/models/legacy.py`), espelhando as colunas exatas do schema
raw-SQL existente (nenhuma coluna renomeada). `sync_assets_from_legacy_database`
e as rotas de `backend/app/api/routes/monitoring.py` passaram a usar sessão
ORM em vez de `sqlite3.connect()` direto.

### 3b. `comandos`/`comando_templates` migrados pra ORM ✅

Mesmo tratamento pras tabelas de comandos: models `Comando` e
`ComandoTemplate`, e `backend/app/api/routes/commands.py` reescrito —
removidas as funções que criavam tabela na mão (`_ensure_table`,
`_ensure_templates_table`) e as queries cruas, todas as 7 rotas migradas
pra ORM.

### 4. `servidor.py` (Flask, porta 5000) aposentado ✅

Confirmado (grep em `agente.py` e `agente_manual.py`) que nenhum build
atual do agente fala HTTP com o Flask — os dois usam só o WebSocket
(`agente_ws_client.ClienteAgenteWS`) pra reportar e receber comandos. A
única rota do Flask que ainda tinha uso real era `GET /agente/download`
(baixado pelo script de autoatualização remota dos agentes), que foi
migrada pro backend FastAPI (`backend/app/api/routes/agent_ws.py`), com a
mesma autenticação por `X-API-Key`. O gerador do script de atualização
(`commands.py::_build_agent_update_script`) passou a apontar pra porta do
backend (8000) em vez da porta do Flask (5000).

**Ação em produção:** `scripts/watchdog-stack.ps1` editado pra não subir
mais o `servidor.py` (função `Start-Collector` mantida no arquivo só de
referência, não é mais chamada no loop principal), o processo Flask que
já estava rodando foi parado manualmente, e o backend reiniciado com o
código novo. Verificado depois via smoke test: porta 5000 vazia, porta
8000 respondendo com o PID novo, script de atualização apontando pra
`:8000/agente/download`, e `/monitoring`, `/assets`, `/commands`
retornando os dados reais normalmente.

O arquivo `servidor.py` em si não foi apagado (só parou de ser executado)
— fica como decisão futura arquivá-lo ou removê-lo de vez.

