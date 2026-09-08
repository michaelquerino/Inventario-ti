# 🎯 GUIA PRÁTICO - Como Testar o Sistema

## 📍 Status Atual

✅ **Backend**: Rodando em http://localhost:8000
✅ **Rate Limiting**: Ativo em todos os endpoints
✅ **Índices BD**: Implementados em `assets.category`
⏳ **Frontend**: Pronto para rodar em http://localhost:3000

---

## 🌐 Acessar a API

### 1. Documentação Swagger (Interativa)
```
http://localhost:8000/docs
```
Aqui você pode:
- Ver todos os endpoints disponíveis
- Testar requisições diretamente na interface
- Ver exemplos de request/response

### 2. Alternativa: ReDoc (Documentação em Leitura)
```
http://localhost:8000/redoc
```

---

## 🔐 Testar Autenticação

### Endpoints Disponíveis

#### 1. Login
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "password"
  }'
```

**Resposta:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

#### 2. Verificar Usuário Atual
```bash
# Use o token retornado acima
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -X GET http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

---

## 📦 Testar Assets (Inventário)

### 1. Listar Assets
```bash
curl -X GET http://localhost:8000/api/v1/assets \
  -H "Authorization: Bearer $TOKEN"
```

### 2. Criar Asset
```bash
curl -X POST http://localhost:8000/api/v1/assets \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_tag": "COMP-001",
    "name": "Computador Dell",
    "category": "Computador",
    "serial_number": "ABC123456",
    "brand": "Dell",
    "model": "OptiPlex 7090",
    "location": "Sala 101",
    "owner": "João Silva",
    "department": "TI"
  }'
```

### 3. Obter Asset Específico
```bash
curl -X GET http://localhost:8000/api/v1/assets/1 \
  -H "Authorization: Bearer $TOKEN"
```

### 4. Atualizar Asset
```bash
curl -X PUT http://localhost:8000/api/v1/assets/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "location": "Sala 102",
    "status": "inactive"
  }'
```

### 5. Deletar Asset
```bash
curl -X DELETE http://localhost:8000/api/v1/assets/1 \
  -H "Authorization: Bearer $TOKEN"
```

---

## 🚦 Testar Rate Limiting

### Via Script Python
```bash
cd C:\Users\Admin\inventario-empresarial
python rate_limit_test.py
```

Este script testa:
- ✅ Limite de login (5/min)
- ✅ Limite de listagem de assets (100/min)
- ✅ Limite de deleção (10/min)

### Via Swagger
1. Acesse http://localhost:8000/docs
2. Vá para POST /auth/login
3. Clique em "Try it out"
4. Clique em "Execute" 6 vezes seguidas
5. A 6ª requisição retornará: **429 Too Many Requests**

### Via Curl (Manual)
```bash
# Teste login com limite de 5/min
for i in {1..6}; do
  echo "Tentativa $i:"
  curl -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@example.com","password":"password"}' \
    -w "\nStatus: %{http_code}\n\n"
  sleep 1
done

# Resultado esperado:
# Tentativa 1-5: HTTP 200 ou 401 (ok)
# Tentativa 6: HTTP 429 (rate limit)
```

---

## 💾 Verificar Índices no Banco

### SQLite (Desenvolvimento)
```bash
cd backend
sqlite3 inventario.db

# Dentro do SQLite:
.indices assets

# Output esperado:
# ix_assets_id
# ix_assets_asset_tag
# ix_assets_serial_number
# ix_assets_category    ← Novo índice
```

### PostgreSQL (Produção)
```sql
\d assets
-- Procure por "ix_assets_category" no output
```

---

## 🎨 Rodar Frontend

### Pré-requisitos
- Node.js v18+ instalado
- npm ou yarn

### Instalação e Execução
```bash
cd C:\Users\Admin\inventario-empresarial\frontend

# Instalar dependências (primeira vez)
npm install

# Rodar em desenvolvimento
npm run dev

# Acessar em http://localhost:3000
```

### Build para Produção
```bash
npm run build
npm start
```

---

## 📊 Monitorar o Servidor

### Ver Logs em Tempo Real
```bash
# Terminal que está rodando o servidor
# (já está visualizando os logs automaticamente)

# Você verá:
# INFO:     Uvicorn running on http://0.0.0.0:8000
# INFO:     Application startup complete
# INFO:     127.0.0.1:12345 - "POST /api/v1/auth/login HTTP/1.1" 200 OK
```

### Parar o Servidor
Pressione **CTRL + C** no terminal que está rodando o uvicorn

---

## 🔍 Verificar Banco de Dados

### Visualizar Dados
```bash
cd backend
sqlite3 inventario.db

# Ver todos os assets
SELECT id, asset_tag, name, category FROM assets;

# Ver logs de auditoria
SELECT actor_email, action, entity_type, created_at FROM audit_logs ORDER BY created_at DESC;

# Ver índices
.indices assets
```

---

## ✅ Checklist de Testes

- [ ] Acessar http://localhost:8000/docs (Swagger)
- [ ] Testar login (POST /auth/login)
- [ ] Testar obter usuário (GET /auth/me)
- [ ] Listar assets (GET /assets)
- [ ] Criar asset (POST /assets)
- [ ] Atualizar asset (PUT /assets/{id})
- [ ] Deletar asset (DELETE /assets/{id})
- [ ] Testar rate limit em login (fazer 6 requisições)
- [ ] Verificar índices no banco (SQLite)
- [ ] Rodar frontend (http://localhost:3000)

---

## 🐛 Troubleshooting

### Erro: "Connection refused" na porta 8000
**Solução:** O servidor não está rodando. Execute:
```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Erro: "Module not found: slowapi"
**Solução:** Instale as dependências:
```bash
cd backend
pip install -r requirements.txt
```

### Erro: "Credenciais inválidas" no login
**Solução:** Verifique o .env:
```bash
# Arquivo: backend/.env
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=password
```

### Rate limit não funciona
**Verificação:**
1. Verifique se `slowapi` está instalado: `pip list | grep slowapi`
2. Verifique se o middleware está em `main.py`: `app.add_middleware(SlowAPIMiddleware)`
3. Verifique os decoradores em `routes/auth.py` e `routes/assets.py`

---

## 📞 Próximos Passos

1. ✅ Testar o que foi implementado (rate limiting + índices)
2. ⏳ Implementar testes automatizados
3. ⏳ Adicionar HTTPS/SSL para produção
4. ⏳ Implementar queue local para offline
5. ⏳ Melhorar documentação

---

**Última atualização:** 2026-08-05
