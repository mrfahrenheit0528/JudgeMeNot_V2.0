document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('particleCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let particles = [];
    const COUNT = 70, CONN = 130;
    let mouse = { x: -999, y: -999 };

    function isDark() { return document.documentElement.classList.contains('dark-theme'); }

    function resize() { canvas.width = window.innerWidth; canvas.height = window.innerHeight; }
    window.addEventListener('resize', resize);
    resize();

    class P {
        constructor() { this.reset(); }
        reset() {
            this.x = Math.random() * canvas.width;
            this.y = Math.random() * canvas.height;
            this.vx = (Math.random() - 0.5) * 0.4;
            this.vy = (Math.random() - 0.5) * 0.4;
            this.r = Math.random() * 2 + 1;
            this.a = Math.random() * 0.5 + 0.3;
        }
        update() {
            this.x += this.vx; this.y += this.vy;
            if (this.x < 0 || this.x > canvas.width) this.vx *= -1;
            if (this.y < 0 || this.y > canvas.height) this.vy *= -1;
            const dx = this.x - mouse.x, dy = this.y - mouse.y;
            const d = Math.sqrt(dx * dx + dy * dy);
            if (d < 120) { this.vx += dx / d * 0.18; this.vy += dy / d * 0.18; }
            this.vx *= 0.99; this.vy *= 0.99;
        }
        draw() {
            const dark = isDark();
            const color = dark ? '96,165,250' : '59,130,246';
            const alpha = dark ? this.a : this.a * 0.6;
            ctx.beginPath(); ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${color},${alpha})`; ctx.fill();
        }
    }
    for (let i = 0; i < COUNT; i++) particles.push(new P());

    (function loop() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        const dark = isDark();
        const lineColor = dark ? '96,165,250' : '59,130,246';
        const lineAlphaMax = dark ? 0.15 : 0.1;
        particles.forEach(p => { p.update(); p.draw(); });
        for (let i = 0; i < particles.length; i++)
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x, dy = particles[i].y - particles[j].y;
                const d = Math.sqrt(dx * dx + dy * dy);
                if (d < CONN) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(${lineColor},${lineAlphaMax * (1 - d / CONN)})`;
                    ctx.lineWidth = 0.6; ctx.stroke();
                }
            }
        requestAnimationFrame(loop);
    })();

    window.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; });
    window.addEventListener('mouseleave', () => { mouse.x = -999; mouse.y = -999; });
});
