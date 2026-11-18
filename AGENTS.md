# EasyRGB: instruções para agentes de IA

Vale para qualquer agente que rode comandos no PC do usuário (Claude Code, Codex, Gemini CLI, Cursor, Copilot...).
A ideia do EasyRGB é que **tudo que der para automatizar, o agente faz**: identificar o hardware, configurar e criar os visuais.

EasyRGB é um controlador RGB por paletas em cima do OpenRGB 1.1 (servidor SDK na porta 6742, roda como admin, driver PawnIO).
App em `app/rgb_controller.py` (servidor local + CLI), interface em `app/index.html` (http://127.0.0.1:6750), aberto pelo `EasyRGB.bat`.
Todos os comandos abaixo rodam dentro da pasta `app/`.

## 0. Configuração guiada (o prompt do `START-HERE.txt`, do README e do botão no app)

O EasyRGB é um **template**: a pessoa baixa a pasta, abre você nela e cola o prompt, muitas vezes **antes de abrir o app
pela primeira vez**. Ela pode ser leiga: fale simples, no idioma dela, e faça você o trabalho. Quando receber esse pedido:

1. **Instale, se faltar** (do zero, sem a pessoa abrir nada):
   - Sem Python 3: ofereça instalar (`winget install -e --id Python.Python.3.12`) e confirme antes.
   - Sem `configurado.ok` na raiz, ou `detectar` dizendo que falta OpenRGB/driver: avise que o Windows vai pedir
     administrador e rode `powershell -NoProfile -ExecutionPolicy Bypass -File "1-Configurar (admin).ps1"` na raiz.
     O script espera terminar; ele baixa o OpenRGB oficial, a biblioteca, o driver PawnIO e desliga o Polychrome.
   - Abra o OpenRGB com `python rgb_controller.py conectar` (dentro de `app/`).
2. Rode `detectar` e conte, em 2 ou 3 frases simples, o que encontrou (placa, RAMs, periféricos, conflitos).
3. Pergunte **uma coisa de cada vez**, sempre com opções curtas para escolher (o usuário pode responder com outra coisa):
   1. Estilo: um jogo, um clima (neon, pôr do sol, gelo...), cores favoritas ou um preset de `app/palettes.json`.
   2. Em quais dispositivos aplicar (liste os que `detectar` achou; os que ficarem de fora mantêm as cores atuais).
   3. Se houver 2+ RAMs: separadas, iguais ou contínuas.
   4. Efeito: estático, um animado do app (precisa do app aberto) ou um efeito do chip (roda sozinho).
   5. Modo jogo (ofereça os jogos de `jogos`) e horários (ex.: modo noite).
   6. Restaurar as cores ao ligar o PC, explicando o motivo com base no campo `persist` de cada dispositivo.
4. Aplique com `ia`, salve o perfil com `configurar` (é ele que marca o PC como configurado e tira o aviso do
   `EasyRGB.bat`), use `automacao` e (se aceito) `iniciar-com-windows sim`.
5. Mostre um resumo curto e diga que, para mexer sozinho depois, é só abrir o `EasyRGB.bat`.

### O que cada dispositivo guarda sozinho (`persist` em `detectar`)

- `auto`: o chip guarda a cor ao desligar o PC (ex.: placas ASRock).
- `manual`: guarda só uma cor fixa, com `save: true` / botão "Gravar na placa" (ex.: alguns teclados).
- `none`: perde a cor ao desligar (ex.: RAMs ENE). Para esses, recomende "restaurar cores ao ligar o PC".

"Restaurar ao ligar o PC" é leve: ao ligar, devolve as cores e **fecha tudo sozinho** (OpenRGB incluído). Só fica aberto
em segundo plano (~30 MB do EasyRGB + ~60 MB do OpenRGB) se houver modo jogo, horários ou efeito animado do app.

## 1. Configurar o PC (faça na primeira conversa, ou quando o usuário pedir)

1. **Detecte o hardware**: `python rgb_controller.py detectar`. Sai um JSON com placa-mãe, BIOS, CPU, RAM, GPU,
   periféricos USB, dispositivos que o OpenRGB enxerga (zonas, LEDs e efeitos nativos de cada um),
   softwares RGB de fabricante instalados ou rodando e `next_steps` com o que falta.
2. **Resolva o que faltar**, explicando ao usuário em linguagem simples:
   - `openrgb_installed` / `pawnio_driver` falsos: peça para ele abrir o `EasyRGB.bat` (instala tudo, pede admin uma vez).
   - `openrgb_running` falso: rode `python rgb_controller.py conectar`.
   - `rgb_software_conflicts` com `running: true`: só é problema se esse programa controla os mesmos dispositivos que o
     OpenRGB (ex.: Armoury Crate numa placa ASUS). Explique e **pergunte antes** de desativar a inicialização dele.
     Desative de forma reversível (tarefa agendada ou serviço em modo manual). Nunca desinstale nada.
   - Placa ou RAM com RGB que não aparece em `openrgb_devices`: confira https://openrgb.org/devices.html, se o OpenRGB
     está como admin e se o RGB não está desligado na BIOS. Conte ao usuário o que encontrou.
3. **Salve o perfil do PC** com o que você descobriu. O app mostra "Configurado por IA" e usa os apelidos:
   ```bash
   python rgb_controller.py configurar - <<'EOF'
   {"agent": "Nome do agente",
    "summary": "ASRock X570 Phantom Gaming 4, 2 RAMs ENE com RGB, teclado RGB",
    "motherboard": "ASRock X570 Phantom Gaming 4",
    "nicknames": {"0": "Placa-mãe", "3": "Teclado"},
    "links": {"DRAM": "span"},
    "notes": ["Logitech G HUB controla só o mouse; não conflita."]}
   EOF
   ```
   - `nicknames`: id do dispositivo (de `detectar`) -> nome amigável.
   - `links`: padrão de agrupamento por tipo (`DRAM`, `GPU`...): `separate`, `mirror` (iguais) ou `span` (contínuas).
4. **Aplique um primeiro visual** que combine com o PC (pergunte o gosto do usuário, ou use um preset).

## 2. Criar visuais: o usuário descreve um clima e você aplica

Monte um perfil e aplique direto, sem perguntar:

```bash
python rgb_controller.py ia - <<'EOF'
{"name": "Nome curto", "description": "Uma frase sobre o visual",
 "colors": ["#FF2E88", "#9B3DFF", "#00D9C8"],
 "mode": "gradiente",
 "brightness": 100,
 "effect": "static", "speed": 3,
 "zones": [{"device": "teclado", "color": "#FFFFFF"},
           {"device": "placa", "zone": "IO Cover", "color": "#FF0000"}],
 "hw": [{"device": "ram", "mode": "Chase", "speed": 60}],
 "links": {"ram": "span"},
 "exclude": [],
 "save": false}
EOF
```

No PowerShell, salve o JSON num arquivo e rode `python rgb_controller.py ia perfil.json`.

- `mode`: `gradiente`, `alternado` ou `zona` (uma cor da paleta por zona).
- `effect`: efeito animado pelo app, em todos os dispositivos: `static`, `fluir`, `respirar`, `ciclo`, `arcoiris`,
  `musica` (reage ao som do PC) ou `temperatura` (cor pela temperatura; ajuste em `automacao.extras`).
  `speed` vai de 1 a 10. Só roda enquanto o EasyRGB está aberto.
- `hw`: efeito **nativo do chip** de um dispositivo (nomes exatos vêm de `detectar` ou `listar`, ex.: `Breathing`,
  `Chase`, `Rainbow`). `speed` de 0 a 100. Roda sozinho, mesmo com o app fechado. Efeitos com `colors: "led"` ou
  `"mode"` usam as cores da paleta; `"none"` usam as cores próprias do chip.
- `device` aceita `placa`, `ram`, `teclado`, `mouse`, `gpu`, o id (`0`..) ou parte do nome. `zone` é opcional.
- `links`: agrupa dispositivos do mesmo tipo. `separate`, `mirror` (iguais) ou `span` (gradiente contínuo).
- `exclude`: dispositivos que ficam de fora.
- `save: true` grava na memória da placa e das RAMs (continua depois de reiniciar). Use só quando o usuário quiser fixar.
- O perfil aparece no card "Cores com IA" da interface, com histórico, e a tela atualiza sozinha.
- Prefira cores vivas e saturadas: cinza e tons escuros ficam feios em LED.
- Presets prontos (jogos e clássicos) ficam em `app/palettes.json`; dá para usar como ponto de partida.

## 3. Automação: jogos, horários e iniciar com o Windows

Quando o usuário pedir algo como "quando eu abrir o Valorant, deixa vermelho" ou "à noite diminui o brilho":

1. `python rgb_controller.py jogos` lista os jogos conhecidos instalados (Steam, Epic, Riot, Xbox) e o preset sugerido.
2. `python rgb_controller.py automacao` mostra as regras atuais. Para salvar, **leia as atuais e mande a lista completa**
   (o comando substitui tudo):
   ```bash
   python rgb_controller.py automacao - <<'EOF'
   {"enabled": true,
    "games": [{"process": "VALORANT-Win64-Shipping.exe", "preset": "Valorant"},
              {"process": "cs2.exe", "preset": "Counter-Strike 2"}],
    "schedule": [{"time": "23:00", "action": "brightness", "value": 20},
                 {"time": "08:00", "action": "restore"},
                 {"time": "19:00", "action": "preset", "value": "Synthwave"}]}
   EOF
   ```
   - `games`: enquanto o executável estiver aberto, usa o preset; ao fechar, volta ao visual do usuário.
     O preset precisa existir em `app/palettes.json` (crie um antes, se for novo).
   - `schedule[].action`: `preset` (value = nome), `brightness` (value = %), `off` (apaga) ou `restore` (visual salvo).
   - Funciona enquanto o EasyRGB está aberto (ou iniciado com o Windows).
3. `python rgb_controller.py iniciar-com-windows sim` cria uma tarefa no logon que devolve as cores depois de reiniciar e
   fecha sozinho quando nada precisa ficar rodando (pede admin uma vez). **Pergunte antes**: é uma mudança no sistema.
   `nao` remove.

## Presets, teclado, atalhos e bandeja

- Presets padrão ficam em `app/palettes.json` (não edite). Os do usuário ficam em `app/my_presets.json`
  (crie pelo app ou escrevendo nesse arquivo: `{"Nome": ["#RRGGBB", ...]}`).
- Teclado: cor por tecla com chaves `"L<índice>"` em `overrides` (índices e nomes em `led_names` do `detectar`).
- `automacao` aceita `"hotkeys": true` (atalhos Ctrl+Alt + setas/E/L) e `"extras": {"temp_source": "gpu"|"cpu",
  "temp_min": 40, "temp_max": 80}`. O EasyRGB roda sem janela, com ícone na bandeja; erros em `app/easyrgb.log`.

## Outros comandos

- `python rgb_controller.py listar`: dispositivos, zonas e efeitos do chip.
- `python rgb_controller.py aplicar <preset ou cores> [--brilho 80] [--modo zona] [--gravar]`
- `python rgb_controller.py compartilhar` / `importar EASYRGB1-...`: código para trocar visuais entre pessoas.
- `python rgb_controller.py desligar`

## Testes

- `python -m unittest discover -s tests -v`: lógica de cores, hardware simulado, automação, API, interface e
  paridade Python x JavaScript (precisa do Node.js para esta última). Rode depois de qualquer mudança.
- `EASYRGB_HW=1 python -m unittest tests.test_hardware -v`: teste no hardware real (as luzes piscam e voltam no final).

## Notas para agentes

- Se o agente roda em sandbox, os comandos precisam de acesso à rede local (portas 6742 e 6750) e aos arquivos reais.
- `detectar` leva alguns segundos (consulta o Windows via PowerShell).

## Convenções do código

- Interface com ícones SVG (estilo Lucide), nunca emojis. Visual sóbrio: fundo zinc escuro, botão primário branco.
- A lógica de cores existe em dois lugares e precisa ficar igual: `plan_colors` no Python e `plan()` no `index.html`.
- `.gitignore` deixa de fora o estado de cada PC (`last_state.json`, `claude_color.json`, `pc.json`, `automations.json`).
