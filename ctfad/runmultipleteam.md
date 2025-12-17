for i in $(seq 1 10); do
  ip="10.10.0.$((99 + i))"   # 10.10.0.100–10.10.0.109
  project="hhf-team$(printf '%02d' "$i")"
  CHALLENGE_IP="$ip" docker compose -p "$project" up -d
done