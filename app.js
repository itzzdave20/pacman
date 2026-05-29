const MAZE_MAP = [
  "############################",
  "#............##............#",
  "#.####.#####.##.#####.####.#",
  "#o####.#####.##.#####.####o#",
  "#.####.#####.##.#####.####.#",
  "#..........................#",
  "#.####.##.########.##.####.#",
  "#......##....##....##......#",
  "######.#####.##.#####.######",
  "#....#................#....#",
  "#.##.#.####.####.####.#.##.#",
  "#....#................#....#",
  "####.#.##.########.##.#.####",
  "####.#.##....##....##.#.####",
  "#........##.####.##........#",
  "####.#.##.########.##.#.####",
  "####.#.##....##....##.#.####",
  "#....#................#....#",
  "#.##.#.####.####.####.#.##.#",
  "#....#................#....#",
  "######.#####.##.#####.######",
  "#......##....##....##......#",
  "#.####.##.########.##.####.#",
  "#..........................#",
  "#.####.#####.##.#####.####.#",
  "#o####.#####.##.#####.####o#",
  "#.####.#####.##.#####.####.#",
  "#............##............#",
  "############################",
];

const canvas = document.getElementById("game-canvas");
const ctx = canvas.getContext("2d");
const scoreEl = document.getElementById("score");
const livesEl = document.getElementById("lives");
const difficultyEl = document.getElementById("difficulty");
const overlay = document.getElementById("overlay");
const overlayTitle = document.getElementById("overlay-title");
const overlayCopy = document.getElementById("overlay-copy");
const loginScreen = document.getElementById("login-screen");
const gameScreen = document.getElementById("game-screen");
const authMessage = document.getElementById("auth-message");
const playerName = document.getElementById("player-name");
const playerPassword = document.getElementById("player-password");

const tile = 30;
const dirs = {
  left: { x: -1, y: 0 },
  right: { x: 1, y: 0 },
  up: { x: 0, y: -1 },
  down: { x: 0, y: 1 },
};
const difficulty = {
  Easy: { pacman: 160, ghost: 86, lives: 5 },
  Medium: { pacman: 150, ghost: 104, lives: 3 },
  Hard: { pacman: 145, ghost: 126, lives: 3 },
};

let users = JSON.parse(localStorage.getItem("pacmanUsers") || "{}");
let currentPlayer = localStorage.getItem("pacmanCurrentPlayer") || "";
let game = null;
let lastTime = 0;
let audioUnlocked = false;
const sounds = {
  opening: new Audio("Music/Opening.mp3"),
  eating: new Audio("Music/Eating.mp3"),
  frenzy: new Audio("Music/Frenzy Eating.mp3"),
  gameOver: new Audio("Music/GameOver.mp3"),
};

for (const sound of Object.values(sounds)) {
  sound.preload = "auto";
}

function saveUsers() {
  localStorage.setItem("pacmanUsers", JSON.stringify(users));
}

async function hashPassword(value) {
  if (!crypto.subtle) return fallbackHash(value);
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function fallbackHash(value) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `local-${(hash >>> 0).toString(16)}`;
}

function showAuth(message, isError = false) {
  authMessage.textContent = message;
  authMessage.style.color = isError ? "var(--danger)" : "var(--cyan)";
}

async function unlockAudio() {
  if (audioUnlocked) return;
  audioUnlocked = true;
  for (const sound of Object.values(sounds)) {
    try {
      sound.volume = 0;
      await sound.play();
      sound.pause();
      sound.currentTime = 0;
      sound.volume = 1;
    } catch {
      sound.volume = 1;
    }
  }
}

function playSound(name) {
  const source = sounds[name];
  if (!source || !audioUnlocked) return;
  source.currentTime = 0;
  source.play().catch(() => {});
}

function startApp() {
  loginScreen.classList.add("hidden");
  gameScreen.classList.remove("hidden");
  restartGame();
}

function centerOf(col, row) {
  return { x: col * tile + tile / 2, y: row * tile + tile / 2 };
}

function cellAt(x, y) {
  return { col: Math.floor(x / tile), row: Math.floor(y / tile) };
}

function isWall(col, row) {
  return row < 0 || row >= MAZE_MAP.length || col < 0 || col >= MAZE_MAP[0].length || MAZE_MAP[row][col] === "#";
}

function validMove(x, y, dir, radius) {
  const nx = x + dir.x;
  const ny = y + dir.y;
  const points = [
    [nx - radius, ny - radius],
    [nx + radius, ny - radius],
    [nx - radius, ny + radius],
    [nx + radius, ny + radius],
  ];
  return points.every(([px, py]) => !isWall(Math.floor(px / tile), Math.floor(py / tile)));
}

function openNeighbors(col, row) {
  return Object.entries(dirs)
    .filter(([, dir]) => !isWall(col + dir.x, row + dir.y))
    .map(([name]) => name);
}

class Game {
  constructor(level) {
    const settings = difficulty[level];
    this.level = level;
    this.score = 0;
    this.lives = settings.lives;
    this.pacSpeed = settings.pacman;
    this.ghostSpeed = settings.ghost;
    this.paused = false;
    this.over = false;
    this.won = false;
    this.frightenedUntil = 0;
    this.pellets = new Map();
    this.powerPellets = new Map();
    this.resetEntities();
    this.buildPellets();
    playSound("opening");
  }

  buildPellets() {
    MAZE_MAP.forEach((row, y) => {
      [...row].forEach((char, x) => {
        if (char === ".") this.pellets.set(`${x},${y}`, true);
        if (char === "o") this.powerPellets.set(`${x},${y}`, true);
      });
    });
  }

  resetEntities() {
    this.pacman = { ...centerOf(13, 23), dir: "left", next: "left", radius: 11, mouth: 0 };
    this.ghosts = [
      { ...centerOf(12, 14), dir: "left", color: "#ff4d6d", home: centerOf(12, 14) },
      { ...centerOf(15, 14), dir: "right", color: "#5ee6ff", home: centerOf(15, 14) },
      { ...centerOf(12, 16), dir: "up", color: "#ff8a3d", home: centerOf(12, 16) },
      { ...centerOf(15, 16), dir: "down", color: "#ff7bd5", home: centerOf(15, 16) },
    ];
  }

  setDirection(dir) {
    if (dirs[dir]) this.pacman.next = dir;
  }

  update(dt, now) {
    if (this.paused || this.over || this.won) return;
    this.movePacman(dt);
    this.ghosts.forEach((ghost, index) => this.moveGhost(ghost, index, dt, now));
    this.checkPellets(now);
    this.checkGhosts(now);
    this.won = this.pellets.size === 0 && this.powerPellets.size === 0;
    if (this.won) showOverlay("You Win!", "Restart for another round.");
  }

  movePacman(dt) {
    const pac = this.pacman;
    const speed = this.pacSpeed * dt;
    if (validMove(pac.x, pac.y, dirs[pac.next], pac.radius)) pac.dir = pac.next;
    if (validMove(pac.x, pac.y, dirs[pac.dir], pac.radius)) {
      pac.x += dirs[pac.dir].x * speed;
      pac.y += dirs[pac.dir].y * speed;
    }
    pac.mouth += dt * 12;
  }

  moveGhost(ghost, index, dt, now) {
    const { col, row } = cellAt(ghost.x, ghost.y);
    const centered = Math.abs(ghost.x - (col * tile + tile / 2)) < 3 && Math.abs(ghost.y - (row * tile + tile / 2)) < 3;
    const frightened = now < this.frightenedUntil;
    if (centered) {
      ghost.x = col * tile + tile / 2;
      ghost.y = row * tile + tile / 2;
      const options = openNeighbors(col, row).filter((name) => name !== opposite(ghost.dir));
      const candidates = options.length ? options : openNeighbors(col, row);
      const target = frightened ? farthestFromPacman(col, row, candidates, this.pacman) : closestToPacman(col, row, candidates, this.pacman, index);
      ghost.dir = target || ghost.dir;
    }
    const speed = (frightened ? this.ghostSpeed * .55 : this.ghostSpeed) * dt;
    if (validMove(ghost.x, ghost.y, dirs[ghost.dir], 10)) {
      ghost.x += dirs[ghost.dir].x * speed;
      ghost.y += dirs[ghost.dir].y * speed;
    } else {
      const options = openNeighbors(col, row);
      ghost.dir = options[Math.floor(Math.random() * options.length)] || "left";
    }
  }

  checkPellets(now) {
    const { col, row } = cellAt(this.pacman.x, this.pacman.y);
    const key = `${col},${row}`;
    if (this.pellets.delete(key)) {
      this.score += 10;
      if (this.score % 50 === 0) playSound("eating");
    }
    if (this.powerPellets.delete(key)) {
      this.score += 50;
      this.frightenedUntil = now + 8000;
      playSound("frenzy");
    }
  }

  checkGhosts(now) {
    for (const ghost of this.ghosts) {
      if (Math.hypot(this.pacman.x - ghost.x, this.pacman.y - ghost.y) > 20) continue;
      if (now < this.frightenedUntil) {
        this.score += 200;
        ghost.x = ghost.home.x;
        ghost.y = ghost.home.y;
        continue;
      }
      this.lives -= 1;
      if (this.lives <= 0) {
        this.over = true;
        playSound("gameOver");
        showOverlay("Game Over", "Restart when you are ready.");
      } else {
        this.resetEntities();
      }
      return;
    }
  }
}

function opposite(dir) {
  return { left: "right", right: "left", up: "down", down: "up" }[dir];
}

function closestToPacman(col, row, options, pacman, offset) {
  return options
    .map((name) => {
      const dir = dirs[name];
      const bias = offset * 1.7;
      return [name, Math.hypot(col + dir.x - pacman.x / tile + bias / tile, row + dir.y - pacman.y / tile)];
    })
    .sort((a, b) => a[1] - b[1])[0]?.[0];
}

function farthestFromPacman(col, row, options, pacman) {
  return options
    .map((name) => {
      const dir = dirs[name];
      return [name, Math.hypot(col + dir.x - pacman.x / tile, row + dir.y - pacman.y / tile)];
    })
    .sort((a, b) => b[1] - a[1])[0]?.[0];
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#02030b";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  drawMaze();
  if (!game) return;
  drawPellets();
  drawPacman();
  drawGhosts();
  scoreEl.textContent = game.score;
  livesEl.textContent = game.lives;
}

function drawMaze() {
  for (let row = 0; row < MAZE_MAP.length; row += 1) {
    for (let col = 0; col < MAZE_MAP[row].length; col += 1) {
      if (MAZE_MAP[row][col] !== "#") continue;
      ctx.fillStyle = "#1029a4";
      ctx.fillRect(col * tile + 2, row * tile + 2, tile - 4, tile - 4);
      ctx.strokeStyle = "#2f66ff";
      ctx.lineWidth = 2;
      ctx.strokeRect(col * tile + 3, row * tile + 3, tile - 6, tile - 6);
    }
  }
}

function drawPellets() {
  ctx.fillStyle = "#fff4c4";
  for (const key of game.pellets.keys()) {
    const [col, row] = key.split(",").map(Number);
    ctx.beginPath();
    ctx.arc(col * tile + tile / 2, row * tile + tile / 2, 3, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.fillStyle = "#ffffff";
  for (const key of game.powerPellets.keys()) {
    const [col, row] = key.split(",").map(Number);
    ctx.beginPath();
    ctx.arc(col * tile + tile / 2, row * tile + tile / 2, 8, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawPacman() {
  const pac = game.pacman;
  const directionAngle = { right: 0, down: Math.PI / 2, left: Math.PI, up: -Math.PI / 2 }[pac.dir];
  const mouth = (Math.sin(pac.mouth) + 1) * .18 + .08;
  ctx.fillStyle = "#ffd426";
  ctx.beginPath();
  ctx.moveTo(pac.x, pac.y);
  ctx.arc(pac.x, pac.y, pac.radius, directionAngle + mouth, directionAngle + Math.PI * 2 - mouth);
  ctx.closePath();
  ctx.fill();
}

function drawGhosts() {
  const frightened = performance.now() < game.frightenedUntil;
  for (const ghost of game.ghosts) {
    ctx.fillStyle = frightened ? "#3d7dff" : ghost.color;
    ctx.beginPath();
    ctx.arc(ghost.x, ghost.y - 2, 12, Math.PI, 0);
    ctx.lineTo(ghost.x + 12, ghost.y + 12);
    ctx.lineTo(ghost.x + 6, ghost.y + 7);
    ctx.lineTo(ghost.x, ghost.y + 12);
    ctx.lineTo(ghost.x - 6, ghost.y + 7);
    ctx.lineTo(ghost.x - 12, ghost.y + 12);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.beginPath();
    ctx.arc(ghost.x - 5, ghost.y - 3, 3, 0, Math.PI * 2);
    ctx.arc(ghost.x + 5, ghost.y - 3, 3, 0, Math.PI * 2);
    ctx.fill();
  }
}

function loop(timestamp) {
  const dt = Math.min((timestamp - lastTime) / 1000 || 0, .05);
  lastTime = timestamp;
  if (game) game.update(dt, timestamp);
  draw();
  requestAnimationFrame(loop);
}

function showOverlay(title, copy) {
  overlayTitle.textContent = title;
  overlayCopy.textContent = copy;
  overlay.classList.remove("hidden");
}

function hideOverlay() {
  overlay.classList.add("hidden");
}

function restartGame() {
  hideOverlay();
  game = new Game(difficultyEl.value);
}

document.getElementById("register-button").addEventListener("click", async () => {
  const name = playerName.value.trim();
  const password = playerPassword.value;
  if (!name || !password) return showAuth("Enter a player name and password.", true);
  if (users[name]) return showAuth("That player already exists.", true);
  users[name] = { passwordHash: await hashPassword(password), bestScore: 0 };
  saveUsers();
  showAuth("Registered. You can log in now.");
});

document.getElementById("login-button").addEventListener("click", async () => {
  const name = playerName.value.trim();
  const password = playerPassword.value;
  if (!users[name]) return showAuth("Player not found. Register first.", true);
  if (users[name].passwordHash !== await hashPassword(password)) return showAuth("Wrong password.", true);
  await unlockAudio();
  currentPlayer = name;
  localStorage.setItem("pacmanCurrentPlayer", name);
  startApp();
});

document.getElementById("pause-button").addEventListener("click", () => {
  if (!game || game.over || game.won) return;
  game.paused = !game.paused;
  document.getElementById("pause-button").textContent = game.paused ? "Resume" : "Pause";
  if (game.paused) showOverlay("Paused", "Tap Resume to continue.");
  else hideOverlay();
});

document.getElementById("restart-button").addEventListener("click", restartGame);
document.getElementById("logout-button").addEventListener("click", () => {
  localStorage.removeItem("pacmanCurrentPlayer");
  gameScreen.classList.add("hidden");
  loginScreen.classList.remove("hidden");
});
difficultyEl.addEventListener("change", restartGame);

window.addEventListener("keydown", (event) => {
  const map = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down", a: "left", d: "right", w: "up", s: "down" };
  if (map[event.key]) {
    event.preventDefault();
    game?.setDirection(map[event.key]);
  }
  if (event.key.toLowerCase() === "p") document.getElementById("pause-button").click();
});

document.querySelectorAll(".touch-pad button").forEach((button) => {
  button.addEventListener("pointerdown", async () => {
    await unlockAudio();
    game?.setDirection(button.dataset.dir);
  });
});

canvas.addEventListener("pointerdown", unlockAudio);

let swipeStart = null;
canvas.addEventListener("touchstart", (event) => {
  const touch = event.changedTouches[0];
  swipeStart = { x: touch.clientX, y: touch.clientY };
}, { passive: true });
canvas.addEventListener("touchend", (event) => {
  if (!swipeStart) return;
  const touch = event.changedTouches[0];
  const dx = touch.clientX - swipeStart.x;
  const dy = touch.clientY - swipeStart.y;
  if (Math.max(Math.abs(dx), Math.abs(dy)) > 24) {
    game?.setDirection(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up"));
  }
  swipeStart = null;
}, { passive: true });

if (currentPlayer && users[currentPlayer]) {
  playerName.value = currentPlayer;
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js").catch(() => {});
  });
}

requestAnimationFrame(loop);
