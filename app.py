#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2026世界杯竞猜平台 - Flask后端
"""

import json
import os
import copy
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder='static', static_url_path='/')

# 允许跨域访问（GitHub Pages前端）
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
MATCHES_FILE = os.path.join(DATA_DIR, 'matches.json')
BETS_FILE = os.path.join(DATA_DIR, 'bets.json')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')

BEIJING_TZ = timezone(timedelta(hours=8))

def load_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def now_bj():
    return datetime.now(BEIJING_TZ)

def parse_match_time(time_str):
    """解析比赛时间字符串 '2026-06-12 09:00' 返回北京时间的datetime"""
    return datetime.strptime(time_str, '%Y-%m-%d %H:%M').replace(tzinfo=BEIJING_TZ)

# ===== 静态文件服务 =====
@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/admin')
def admin():
    return send_from_directory(app.static_folder, 'admin.html')

# ===== 用户注册/登录 =====
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    nickname = data.get('nickname', '').strip()
    if not nickname or len(nickname) > 20:
        return jsonify({'ok': False, 'msg': '昵称无效'})
    users = load_json(USERS_FILE, {})
    reg_time = now_bj().strftime('%Y-%m-%d %H:%M:%S')
    if nickname not in users:
        users[nickname] = {
            'nickname': nickname,
            'registered_at': reg_time,
            'last_login': reg_time
        }
        save_json(USERS_FILE, users)
    else:
        users[nickname]['last_login'] = reg_time
        save_json(USERS_FILE, users)
    return jsonify({'ok': True, 'nickname': nickname})

# ===== 获取所有比赛数据 =====
@app.route('/api/matches', methods=['GET'])
def get_matches():
    matches = load_json(MATCHES_FILE, [])
    return jsonify({'ok': True, 'matches': matches})

# ===== 获取分组和积分榜数据 =====
@app.route('/api/standings', methods=['GET'])
def get_standings():
    matches = load_json(MATCHES_FILE, [])
    # 构建小组积分榜
    groups = {}
    for match in matches:
        g = match.get('group', '')
        if g not in groups:
            groups[g] = {}
        for team_key in ['home_team', 'away_team']:
            team = match.get(team_key, '')
            if team and team not in groups[g]:
                groups[g][team] = {'played': 0, 'win': 0, 'draw': 0, 'loss': 0, 'goals_for': 0, 'goals_against': 0, 'pts': 0}
        # 如果比赛已结束，更新积分
        if match.get('status') == 'finished' and match.get('home_score') is not None and match.get('away_score') is not None:
            ht = match['home_team']
            at = match['away_team']
            hs = match['home_score']
            as_ = match['away_score']
            groups[g][ht]['played'] += 1
            groups[g][at]['played'] += 1
            groups[g][ht]['goals_for'] += hs
            groups[g][ht]['goals_against'] += as_
            groups[g][at]['goals_for'] += as_
            groups[g][at]['goals_against'] += hs
            if hs > as_:
                groups[g][ht]['win'] += 1
                groups[g][ht]['pts'] += 3
                groups[g][at]['loss'] += 1
            elif hs == as_:
                groups[g][ht]['draw'] += 1
                groups[g][at]['draw'] += 1
                groups[g][ht]['pts'] += 1
                groups[g][at]['pts'] += 1
            else:
                groups[g][ht]['loss'] += 1
                groups[g][at]['win'] += 1
                groups[g][at]['pts'] += 3
    # 排序
    result = {}
    for g in sorted(groups.keys()):
        teams = list(groups[g].items())
        teams.sort(key=lambda x: (-x[1]['pts'], -(x[1]['goals_for'] - x[1]['goals_against']), -x[1]['goals_for']))
        result[g] = [{'team': t[0], **t[1]} for t in teams]
    return jsonify({'ok': True, 'groups': result})

# ===== 提交竞猜 =====
@app.route('/api/bet', methods=['POST'])
def place_bet():
    data = request.json
    nickname = data.get('nickname', '').strip()
    match_id = data.get('match_id')
    home_score = data.get('home_score')
    away_score = data.get('away_score')
    
    if not nickname or not match_id:
        return jsonify({'ok': False, 'msg': '参数不完整'})
    if home_score is None or away_score is None:
        return jsonify({'ok': False, 'msg': '请输入比分'})
    try:
        home_score = int(home_score)
        away_score = int(away_score)
    except:
        return jsonify({'ok': False, 'msg': '比分必须是数字'})
    if home_score < 0 or away_score < 0:
        return jsonify({'ok': False, 'msg': '比分不能为负数'})
    if home_score > 20 or away_score > 20:
        return jsonify({'ok': False, 'msg': '比分不合理'})
    
    matches = load_json(MATCHES_FILE, [])
    match = None
    for m in matches:
        if m['id'] == match_id:
            match = m
            break
    if not match:
        return jsonify({'ok': False, 'msg': '比赛不存在'})
    
    # 检查比赛是否已经开始（开赛前5分钟锁定）
    match_time = parse_match_time(match['time'])
    if now_bj() >= match_time - timedelta(minutes=5):
        return jsonify({'ok': False, 'msg': '比赛已临近开赛或已开始，无法修改竞猜'})
    if match.get('status') == 'finished':
        return jsonify({'ok': False, 'msg': '比赛已结束'})
    
    bets = load_json(BETS_FILE, {})
    if match_id not in bets:
        bets[match_id] = {}
    
    # 预测结果
    predicted_result = 'home' if home_score > away_score else ('draw' if home_score == away_score else 'away')
    
    bets[match_id][nickname] = {
        'nickname': nickname,
        'home_score': home_score,
        'away_score': away_score,
        'predicted_result': predicted_result,
        'bet_at': now_bj().strftime('%Y-%m-%d %H:%M:%S')
    }
    save_json(BETS_FILE, bets)
    return jsonify({'ok': True, 'msg': '竞猜提交成功'})

# ===== 获取某场比赛的竞猜情况 =====
@app.route('/api/bets/<match_id>', methods=['GET'])
def get_match_bets(match_id):
    bets = load_json(BETS_FILE, {})
    match_bets = bets.get(match_id, {})
    if not isinstance(match_bets, dict):
        match_bets = {}
    return jsonify({
        'ok': True,
        'total_betters': len(match_bets),
        'bets': list(match_bets.values())
    })

# ===== 获取某个用户的竞猜记录 =====
@app.route('/api/user_bets/<nickname>', methods=['GET'])
def get_user_bets(nickname):
    bets = load_json(BETS_FILE, {})
    matches = load_json(MATCHES_FILE, [])
    match_map = {m['id']: m for m in matches}
    
    user_bets = []
    for mid, mbets in bets.items():
        if not isinstance(mbets, dict):
            continue
        if nickname in mbets:
            bet = mbets[nickname]
            m = match_map.get(mid, {})
            user_bets.append({
                'match_id': mid,
                'match': m,
                'bet': bet,
                'won_result': m.get('status') == 'finished' and bet.get('predicted_result') == m.get('actual_result'),
                'won_score': m.get('status') == 'finished' and bet.get('home_score') == m.get('home_score') and bet.get('away_score') == m.get('away_score'),
                'stars_earned': m.get('status') == 'finished' and (
                    3 if (bet.get('home_score') == m.get('home_score') and bet.get('away_score') == m.get('away_score'))
                    else (1 if bet.get('predicted_result') == m.get('actual_result') else 0)
                ) or 0
            })
    user_bets.sort(key=lambda x: x['match'].get('time', ''))
    return jsonify({'ok': True, 'bets': user_bets})

# ===== 获取排行榜 =====
@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    bets = load_json(BETS_FILE, {})
    matches = load_json(MATCHES_FILE, [])
    
    # 只统计已结束的比赛
    finished_matches = {m['id']: m for m in matches if m.get('status') == 'finished'}
    
    user_stats = {}
    
    for mid, mbets in bets.items():
        m = finished_matches.get(mid)
        if not m or not isinstance(mbets, dict):
            continue
        for nickname, bet in mbets.items():
            if not isinstance(bet, dict):
                continue
            if nickname not in user_stats:
                user_stats[nickname] = {'total_bets': 0, 'result_correct': 0, 'score_correct': 0, 'stars': 0}
            user_stats[nickname]['total_bets'] += 1
            
            result_ok = bet.get('predicted_result') == m.get('actual_result')
            score_ok = bet.get('home_score') == m.get('home_score') and bet.get('away_score') == m.get('away_score')
            
            if result_ok:
                user_stats[nickname]['result_correct'] += 1
            if score_ok:
                user_stats[nickname]['score_correct'] += 1
                user_stats[nickname]['stars'] += 3
            elif result_ok:
                user_stats[nickname]['stars'] += 1
    
    # 排序：星星数从高到低
    rankings = sorted(user_stats.items(), key=lambda x: (-x[1]['stars'], -x[1]['result_correct']))
    result = []
    for i, (nickname, stats) in enumerate(rankings):
        result.append({
            'rank': i + 1,
            'nickname': nickname,
            'stars': stats['stars'],
            'total_bets': stats['total_bets'],
            'result_correct': stats['result_correct'],
            'score_correct': stats['score_correct'],
            'accuracy': round(stats['result_correct'] / stats['total_bets'] * 100, 1) if stats['total_bets'] > 0 else 0
        })
    return jsonify({'ok': True, 'leaderboard': result})

# ===== 管理员：更新比赛结果 =====
@app.route('/api/admin/update_result', methods=['POST'])
def update_result():
    data = request.json
    match_id = data.get('match_id')
    home_score = data.get('home_score')
    away_score = data.get('away_score')
    
    if not match_id or home_score is None or away_score is None:
        return jsonify({'ok': False, 'msg': '参数不完整'})
    try:
        home_score = int(home_score)
        away_score = int(away_score)
    except:
        return jsonify({'ok': False, 'msg': '比分必须是数字'})
    
    matches = load_json(MATCHES_FILE, [])
    match = None
    for m in matches:
        if m['id'] == match_id:
            match = m
            break
    if not match:
        return jsonify({'ok': False, 'msg': '比赛不存在'})
    
    match['home_score'] = home_score
    match['away_score'] = away_score
    match['status'] = 'finished'
    
    if home_score > away_score:
        match['actual_result'] = 'home'
    elif home_score == away_score:
        match['actual_result'] = 'draw'
    else:
        match['actual_result'] = 'away'
    
    save_json(MATCHES_FILE, matches)
    
    # 如果是淘汰赛，自动生成下一轮对阵
    _generate_next_round(matches)
    
    return jsonify({'ok': True, 'msg': '比赛结果已更新'})

# ===== 管理员：获取所有用户 =====
@app.route('/api/admin/users', methods=['GET'])
def get_users():
    users = load_json(USERS_FILE, {})
    return jsonify({'ok': True, 'users': list(users.keys())})

# ===== 淘汰赛对阵自动生成 =====
def _generate_next_round(matches):
    """根据比赛结果自动生成淘汰赛下一轮对阵"""
    # 先识别淘汰赛阶段匹配规则
    knockout_matches = [m for m in matches if m.get('stage') in ['1/16决赛', '1/8决赛', '1/4决赛', '半决赛']]
    
    stage_order = ['1/16决赛', '1/8决赛', '1/4决赛', '半决赛']
    
    for stage_idx, stage in enumerate(stage_order):
        if stage_idx == len(stage_order) - 1:
            continue  # 半决赛后是决赛和季军战，单独处理
        
        next_stage = stage_order[stage_idx + 1]
        current_stage_matches = [m for m in knockout_matches if m.get('stage') == stage]
        
        # 检查当前轮次是否所有比赛都已完结
        if not current_stage_matches:
            continue
        if not all(m.get('status') == 'finished' for m in current_stage_matches):
            continue
        
        # 检查下一轮是否已经生成
        next_stage_matches = [m for m in knockout_matches if m.get('stage') == next_stage]
        if next_stage_matches:
            continue  # 已经生成过了
        
        # 按比赛序号排列
        current_stage_matches.sort(key=lambda x: x.get('match_number', 0))
        
        # 生成下一轮对阵
        # 规则：第1场的胜者 vs 第2场的胜者，第3场的胜者 vs 第4场的胜者...
        for i in range(0, len(current_stage_matches), 2):
            if i + 1 >= len(current_stage_matches):
                break
            m1 = current_stage_matches[i]
            m2 = current_stage_matches[i + 1]
            
            winner1 = m1.get('home_team') if m1.get('actual_result') == 'home' else (m1.get('away_team') if m1.get('actual_result') == 'away' else None)
            winner2 = m2.get('home_team') if m2.get('actual_result') == 'home' else (m2.get('away_team') if m2.get('actual_result') == 'away' else None)
            
            if not winner1 or not winner2:
                continue
            
            # 生成下一轮比赛ID
            next_match_number = (current_stage_matches[0].get('match_number', 0) // 2) + (i // 2)
            next_id = f"{next_stage}_{next_match_number}"
            
            # 确定比赛时间（默认在上一轮最后一场比赛后1-2天）
            last_match_time = max(
                parse_match_time(m1['time']),
                parse_match_time(m2['time'])
            )
            next_day_offset = 1 if stage == '1/16决赛' else (2 if stage == '1/8决赛' else 3)
            next_time = (last_match_time + timedelta(days=next_day_offset)).strftime('%Y-%m-%d %H:%M')
            
            new_match = {
                'id': next_id,
                'stage': next_stage,
                'match_number': next_match_number,
                'group': next_stage,
                'time': next_time,
                'home_team': winner1,
                'away_team': winner2,
                'status': 'upcoming',
                'home_score': None,
                'away_score': None,
                'actual_result': None
            }
            matches.append(new_match)
        
        save_json(MATCHES_FILE, matches)
    
    # 处理半决赛 -> 决赛/季军战
    semi_matches = [m for m in knockout_matches if m.get('stage') == '半决赛']
    if semi_matches and all(m.get('status') == 'finished' for m in semi_matches):
        semi_matches.sort(key=lambda x: x.get('match_number', 0))
        
        # 检查决赛是否已生成
        finals = [m for m in matches if m.get('stage') == '决赛']
        if not finals and len(semi_matches) >= 2:
            m1, m2 = semi_matches[0], semi_matches[1]
            winner1 = m1.get('home_team') if m1.get('actual_result') == 'home' else (m1.get('away_team') if m1.get('actual_result') == 'away' else None)
            winner2 = m2.get('home_team') if m2.get('actual_result') == 'home' else (m2.get('away_team') if m2.get('actual_result') == 'away' else None)
            loser1 = m1.get('home_team') if m1.get('actual_result') == 'away' else (m1.get('away_team') if m1.get('actual_result') == 'home' else None)
            loser2 = m2.get('home_team') if m2.get('actual_result') == 'away' else (m2.get('away_team') if m2.get('actual_result') == 'home' else None)
            
            last_semi_time = max(parse_match_time(m1['time']), parse_match_time(m2['time']))
            
            if winner1 and winner2:
                matches.append({
                    'id': 'final',
                    'stage': '决赛',
                    'match_number': 0,
                    'group': '决赛',
                    'time': (last_semi_time + timedelta(days=4)).strftime('%Y-%m-%d %H:%M'),
                    'home_team': winner1,
                    'away_team': winner2,
                    'status': 'upcoming',
                    'home_score': None,
                    'away_score': None,
                    'actual_result': None
                })
            if loser1 and loser2:
                matches.append({
                    'id': 'third_place',
                    'stage': '季军战',
                    'match_number': 0,
                    'group': '季军战',
                    'time': (last_semi_time + timedelta(days=3)).strftime('%Y-%m-%d %H:%M'),
                    'home_team': loser1,
                    'away_team': loser2,
                    'status': 'upcoming',
                    'home_score': None,
                    'away_score': None,
                    'actual_result': None
                })
            save_json(MATCHES_FILE, matches)


# ===== 管理员：重置竞猜数据 =====
@app.route('/api/admin/reset_bets', methods=['POST'])
def reset_bets():
    save_json(BETS_FILE, {})
    return jsonify({'ok': True, 'msg': '竞猜数据已重置'})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=8888)