// frontend/app/post/profile/page.tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  getAccountProfile,
  updateAccountProfile,
  type AccountProfileInput,
} from "@/lib/api";

type Field = {
  key: keyof AccountProfileInput;
  label: string;
  placeholder: string;
  rows?: number;
};

const FIELDS: Field[] = [
  {
    key: "niche",
    label: "ジャンル / 専門領域",
    placeholder: "例: 整体院 / 腰痛・肩こり改善",
  },
  {
    key: "target_audience",
    label: "ターゲット視聴者",
    placeholder: "例: 40〜60代でデスクワークの腰痛・肩こりに悩む層",
    rows: 2,
  },
  {
    key: "tone",
    label: "トーン / 語り口",
    placeholder: "例: 安心感のある丁寧な敬語。専門用語は噛み砕く",
    rows: 2,
  },
  {
    key: "goals",
    label: "運用目的",
    placeholder: "例: 来院予約の獲得 / 専門性の訴求",
    rows: 2,
  },
  {
    key: "hashtags",
    label: "定番ハッシュタグ",
    placeholder: "例: #整体 #腰痛改善 #肩こり",
    rows: 2,
  },
  {
    key: "ng_words",
    label: "避ける語 / 表現",
    placeholder: "例: 完治 / 必ず治る などの断定表現",
    rows: 2,
  },
  {
    key: "notes",
    label: "補足メモ",
    placeholder: "その他、生成時に踏まえてほしいこと",
    rows: 3,
  },
];

const EMPTY: AccountProfileInput = {
  niche: "",
  target_audience: "",
  tone: "",
  goals: "",
  hashtags: "",
  ng_words: "",
  notes: "",
};

export default function AccountProfilePage() {
  const [form, setForm] = useState<AccountProfileInput>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const p = await getAccountProfile();
      setForm({
        niche: p.niche ?? "",
        target_audience: p.target_audience ?? "",
        tone: p.tone ?? "",
        goals: p.goals ?? "",
        hashtags: p.hashtags ?? "",
        ng_words: p.ng_words ?? "",
        notes: p.notes ?? "",
      });
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "読み込みに失敗しました");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const saved = await updateAccountProfile(form);
      setSavedAt(saved.updated_at);
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存に失敗しました");
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <div className="mb-6">
        <Link href="/post" className="text-sm text-gray-400 hover:text-white">
          ← 投稿一覧
        </Link>
        <h1 className="mt-1 text-2xl font-bold">アカウント設定</h1>
        <p className="mt-1 text-sm text-gray-400">
          アカウントの性質を登録すると、AI キャプション生成がこの文脈に沿って最適化されます。
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-500/40 bg-red-600/20 p-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-gray-500">読み込み中…</p>
      ) : (
        <div className="space-y-5">
          {FIELDS.map((f) => (
            <label key={f.key} className="block">
              <span className="mb-1 block text-sm font-medium text-gray-300">
                {f.label}
              </span>
              <textarea
                value={form[f.key] ?? ""}
                rows={f.rows ?? 1}
                placeholder={f.placeholder}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, [f.key]: e.target.value }))
                }
                className="w-full resize-y rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:border-blue-500/60 focus:outline-none"
              />
            </label>
          ))}

          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold hover:bg-blue-500 disabled:opacity-50"
            >
              {saving ? "保存中…" : "保存する"}
            </button>
            {savedAt && !saving && (
              <span className="text-xs text-green-400">保存しました</span>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
