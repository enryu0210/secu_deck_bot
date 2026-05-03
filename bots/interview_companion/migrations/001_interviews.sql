-- =====================================================================
-- Interview Companion — 인터뷰 누적 저장 스키마
-- ---------------------------------------------------------------------
-- 봇 시작 시 idempotent 실행. (CREATE TABLE IF NOT EXISTS / 이미 있으면 무해)
-- =====================================================================

-- 인터뷰 본체 (요약·가설검증·인용은 JSONB 로 보관해 스키마 진화 비용 ↓)
CREATE TABLE IF NOT EXISTS interviews (
    id SERIAL PRIMARY KEY,
    -- 같은 사용자(대표)별로 1부터 자동 증가하는 표시용 번호
    interview_number INT,
    target_name TEXT,                       -- 익명화 권장 (이니셜·역할로만 저장)
    target_role TEXT,
    target_company TEXT,
    target_company_size TEXT,
    interview_date DATE,
    raw_notes TEXT,                          -- 녹취 또는 사용자가 직접 입력한 메모
    summary JSONB,                           -- {short, key_points, action_items}
    hypotheses_results JSONB,                -- {[hypothesis_id]: {verdict, evidence}}
    quotes JSONB,                            -- [{text, hypothesis_id, sensitivity}]
    user_id TEXT NOT NULL,                   -- Discord user id (사용자 격리)
    bot_name TEXT NOT NULL DEFAULT 'interview_companion',
    -- 익명화 처리 시각 — 6개월 후 cron 으로 raw_notes/quotes 마스킹
    anonymized_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_interviews_user_date
    ON interviews(user_id, interview_date DESC);
CREATE INDEX IF NOT EXISTS idx_interviews_user_created
    ON interviews(user_id, created_at DESC);

-- 가설 카탈로그 미러 (선택). YAML 이 source of truth, DB 는 검색 편의용.
CREATE TABLE IF NOT EXISTS hypotheses (
    id SERIAL PRIMARY KEY,
    hypothesis_id TEXT UNIQUE NOT NULL,
    statement TEXT NOT NULL,
    priority INT DEFAULT 2,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
