async function loadScoreboard() {
  const response = await fetch('/api/scoreboard');
  if (!response.ok) {
    return;
  }
  const data = await response.json();
  const tbody = document.querySelector('#scoreboard-table tbody');
  const leaderName = document.querySelector('[data-leader-name]');
  const leaderPoints = document.querySelector('[data-leader-points]');
  const leaderCaptures = document.querySelector('[data-leader-captures]');

  if (leaderName && leaderPoints && leaderCaptures) {
    if (data.length) {
      leaderName.textContent = data[0].team;
      leaderPoints.textContent = `${data[0].total} pts`;
      leaderCaptures.textContent = `${data[0].attack_captures} captures • ${data[0].sla_passes} SLA`;
    } else {
      leaderName.textContent = 'Awaiting teams';
      leaderPoints.textContent = '--';
      leaderCaptures.textContent = 'No activity yet';
    }
  }

  tbody.innerHTML = '';
  data.forEach((row) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${row.rank}</td>
      <td>${row.team}</td>
      <td>${row.attack_captures}</td>
      <td>${row.sla_passes}</td>
      <td>${row.attack_points}</td>
      <td>${row.sla_points}</td>
      <td>${row.total}</td>
    `;
    tbody.appendChild(tr);
  });
}

document.addEventListener('DOMContentLoaded', loadScoreboard);
setInterval(loadScoreboard, 15000);
