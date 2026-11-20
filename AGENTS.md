# EasyRGB: instruções para agentes de IA

Vale para qualquer agente que rode comandos no PC do usuário (Claude Code, Codex, Gemini CLI, Cursor, Copilot...).
A ideia do EasyRGB é que **tudo que der para automatizar, o agente faz**: identificar o hardware, configurar e criar os visuais.

EasyRGB é um controlador RGB por paletas em cima do OpenRGB 1.1 (servidor SDK na porta 6742, roda como admin, driver PawnIO).
App em `app/rgb_controller.py` (servidor local + CLI), interface em `app/index.html` (http://127.0.0.1:6750), aberto pelo `EasyRGB.bat`.
Todos os comandos abaixo rodam dentro da pasta `app/`.

## 0. Configuração rápida (o prompt do `START-HERE.txt`, do README e do botão no app)

O EasyRGB é um **template quase pronto**: a pessoa baixa a pasta, abre você nela e cola o prompt, muitas vezes antes
de abrir o app. Ela pode ser leiga. **Configure tudo sozinho, rápido e falando pouco**, no idioma dela.
Só pare para o que está marcado como *pergunte*. O efeito ela escolhe depois, no app.

1. **Instale o que faltar** (só avise que o Windows vai pedir administrador uma vez):
   - Sem Python 3: *pergunte* e instale (`winget install -e --id Python.Python.3.13`).
   - Sem `configurado.ok` na raiz, ou `detectar` dizendo que falta OpenRGB/driver: rode
     `powershell -NoProfile -ExecutionPolicy Bypass -File "1-Configurar (admin).ps1"` na raiz. Ele espera terminar e
     instala o OpenRGB oficial, as bibliotecas (`app/lib/pyXY`, reinstaladas sozinhas se o Python mudar) e o driver
     PawnIO, e desliga o ASRock Polychrome (reversível).
   - Abra o OpenRGB: `python rgb_controller.py conectar` (dentro de `app/`).
2. **Detecte e salve o perfil do PC sem perguntar**: rode `detectar` e depois `configurar` (seção 1) com:
   - `nicknames` amigáveis com a marca quando ajudar (ex.: "Placa-mãe", "Memória RAM", "Teclado Logitech G PRO");
   - `links`: `{"DRAM": "mirror"}` quando houver 2 ou mais RAMs;
   - `vendors` só se precisar mudar o padrão (a ponte com o G HUB já liga sozinha; periférico sem RGB não precisa de nada);
   - `notes`: 1 a 3 frases do que achou.
   - Programa de fabricante brigando pelo mesmo hardware (ex.: Armoury Crate numa placa ASUS): *pergunte* antes de
     desligar a inicialização dele (de forma reversível; nunca desinstale). O Logitech G HUB não é conflito.
3. **Pergunte só uma coisa: o estilo.** Dê 4 a 6 opções curtas de `app/palettes.json` (ex.: GTA VI, Cyberpunk 2077,
   Synthwave, Aurora), mais "um jogo que eu curto" e "minhas cores".
4. **Aplique com `ia`**: a paleta escolhida em todos os dispositivos, `"effect": "static"` e RAMs iguais.
   Não pergunte sobre efeitos, modo jogo nem modo noite: isso fica no app.
5. Se algum dispositivo tiver `persist: "none"` (perde a cor ao desligar), ligue `iniciar-com-windows sim`:
   faz parte da configuração que a pessoa pediu.
6. **Abra o app** (`Start-Process EasyRGB.bat` na raiz) e responda em 3 ou 4 linhas: o que encontrou, o visual
   aplicado, que os efeitos (Computador e cada periférico), o modo jogo e o modo noite ficam no app, e que é só pedir
   novos visuais aqui.

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
   - `vendors` (opcional): periféricos pintados **por cima do programa do fabricante**, sem desativá-lo. Veja
     `vendor_bridges` em `detectar`: cada PC é diferente, então só configure o que existe nele.
     Ex.: `"vendors": {"logitech": {"devices": [{"type": "mouse", "zones": 2, "name": "G502"}]}}`.
     `type`: `mouse`, `keyboard`, `headset`, `mousemat`, `speaker` ou `all` (todas as luzes da marca numa cor só,
     o padrão). `zones` = quantas áreas de luz o aparelho tem. `{"enabled": false}` desliga a ponte.
     Para a Logitech, peça para ligar no G HUB a opção que permite jogos e aplicativos controlarem a iluminação.
     Teclados Logitech que o OpenRGB enxerga são pintados tecla por tecla pelo G HUB automaticamente.
     Hoje existe ponte para **Logitech G HUB**; para outras marcas, use o OpenRGB e avise sobre o conflito.
4. **Aplique um primeiro visual** (na configuração rápida, com a paleta que a pessoa escolheu).

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
  `musica` (reage ao som do PC), `onda` (onda de cores com a paleta; `"direction"`: `direita`, `esquerda`,
  `baixo`, `cima`, `centro` ou `dentro`), `estrelas` (LEDs piscam como estrelas), `tela` (copia as cores da tela)
  ou `teclas` (cada tecla apertada solta um anel de cor). No teclado esses efeitos seguem a posição real das teclas.
- `peripheral_effects` (opcional): efeito próprio de um periférico, separado do computador. Ex.:
  `"effect": "static", "peripheral_effects": {"teclado": "onda"}` deixa placa e RAMs paradas e só o teclado em onda.
  `estrelas`, `tela` e `teclas` são feitos para teclado; use-os aqui em vez de no `effect` do PC inteiro.
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
- `automacao` aceita `"hotkeys": true` (atalhos Ctrl+Alt + setas/E/L). O EasyRGB roda sem janela, com ícone na bandeja; erros em `app/easyrgb.log`.

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
