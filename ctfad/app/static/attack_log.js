const ATTACK_LOG_TZ = 'Asia/Jakarta';
const ATTACK_LOG_TZ_LABEL = 'UTC+7';
const HAS_OFFSET_REGEX = /([zZ]|[+-]\d{2}:?\d{2})$/;

function normalizeToUtc(value) {
  if (!value) return null;
  return HAS_OFFSET_REGEX.test(value) ? value : `${value}Z`;
}

function formatTimestamp(value) {
  const normalized = normalizeToUtc(value);
  if (!normalized) {
    return '—';
  }
  const date = new Date(normalized);
  const time = date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: ATTACK_LOG_TZ,
  });
  const day = date.toLocaleDateString([], { timeZone: ATTACK_LOG_TZ });
  return `${time} <span class="has-text-grey-light">(${day} ${ATTACK_LOG_TZ_LABEL})</span>`;
}

async function loadAttacks() {
  const response = await fetch('/api/attacks');
  if (!response.ok) {
    return;
  }
  const data = await response.json();
  const tbody = document.querySelector('#attack-table tbody');
  if (!tbody) {
    return;
  }

  tbody.innerHTML = '';
  data
    .filter((entry) => entry.valid)
    .forEach((entry) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${formatTimestamp(entry.time)}</td>
        <td>${entry.attacker ?? '—'}</td>
        <td>${entry.defender ?? '—'}</td>
        <td>${entry.challenge ?? '—'}</td>
        <td>
          <span class="tag is-success is-light">Valid Capture</span>
        </td>
      `;
      tbody.appendChild(tr);
    });
}

document.addEventListener('DOMContentLoaded', () => {
  loadAttacks();
  setInterval(loadAttacks, 10000);
});
