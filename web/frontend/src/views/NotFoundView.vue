<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <main class="not-found-page">
    <section class="not-found-panel">
      <div class="orbit" aria-hidden="true">
        <span class="orbit-leaf">◇</span>
      </div>
      <p class="code">404</p>
      <h1>这片叶子不在地图上</h1>
      <p class="description">页面可能已经移动、退役，或地址输入有误。</p>
      <button type="button" @click="router.push('/')">返回对话</button>
    </section>
  </main>
</template>

<style scoped>
.not-found-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  color: var(--moon, #f3f0de);
  background:
    radial-gradient(circle at 50% 38%, rgba(98, 212, 142, 0.14), transparent 32%),
    linear-gradient(160deg, rgba(5, 20, 14, 0.96), rgba(9, 31, 23, 0.9));
}

.not-found-panel {
  width: min(520px, 100%);
  padding: 48px 28px;
  text-align: center;
  border: 1px solid rgba(184, 255, 207, 0.18);
  border-radius: 24px;
  background: rgba(11, 35, 25, 0.62);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.32);
  backdrop-filter: blur(18px);
}

.orbit {
  width: 88px;
  height: 88px;
  margin: 0 auto 18px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(134, 239, 172, 0.35);
  border-radius: 50%;
  box-shadow: inset 0 0 28px rgba(74, 222, 128, 0.12), 0 0 30px rgba(74, 222, 128, 0.08);
}

.orbit-leaf {
  color: #a7f3c0;
  font-size: 42px;
  transform: rotate(24deg);
}

.code {
  margin: 0;
  color: rgba(167, 243, 192, 0.72);
  font: 600 13px/1 'Noto Sans SC', sans-serif;
  letter-spacing: 0.5em;
}

h1 {
  margin: 14px 0 10px;
  font: 600 clamp(24px, 6vw, 34px)/1.35 'Noto Serif SC', serif;
  letter-spacing: 0.08em;
}

.description {
  margin: 0 auto 28px;
  color: rgba(235, 245, 235, 0.68);
  font: 400 14px/1.8 'Noto Sans SC', sans-serif;
}

button {
  min-width: 132px;
  min-height: 44px;
  padding: 0 22px;
  color: #effff4;
  font: 500 14px 'Noto Sans SC', sans-serif;
  letter-spacing: 0.08em;
  border: 1px solid rgba(167, 243, 192, 0.42);
  border-radius: 999px;
  background: linear-gradient(135deg, rgba(49, 146, 91, 0.86), rgba(25, 94, 63, 0.9));
  box-shadow: 0 8px 26px rgba(11, 90, 51, 0.28);
  cursor: pointer;
}

button:hover {
  border-color: rgba(210, 255, 223, 0.72);
  transform: translateY(-1px);
}

button:focus-visible {
  outline: 2px solid #a7f3c0;
  outline-offset: 3px;
}
</style>
