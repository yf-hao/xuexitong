"""AI 主观题评分 vs 教师评分：一致性、偏差结构、修正率与效率指标计算。

用法
----
    python metrics.py --csv grading_study.csv --outdir out/

不带 --csv 时会生成一份合成演示数据，用于验证脚本本身可跑通。
依赖：numpy pandas scipy matplotlib

输入 CSV 列（见《AI评分一致性研究_实验方案.md》第 2.1 节）：
    answer_pid, question_id, question_type, max_score,
    ai_score, teacher_score, final_score,
    teacher_time_ms, review_time_ms, ai_latency_ms,
    teacher_id, ai_attempt, ai_has_image   （后四列可选）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

for _font in ("PingFang SC", "Heiti SC", "Microsoft YaHei", "SimHei", "Arial Unicode MS"):
    if _font in {f.name for f in matplotlib.font_manager.fontManager.ttflist}:
        plt.rcParams["font.sans-serif"] = [_font]
        break
plt.rcParams["axes.unicode_minus"] = False

REQUIRED = ["answer_pid", "question_id", "ai_score", "teacher_score"]


# --------------------------------------------------------------------------
# 核心指标
# --------------------------------------------------------------------------
def quadratic_weighted_kappa(a, b, labels=None):
    """二次加权 Kappa。labels 为有序等级列表；不传则取 a、b 的并集排序。"""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if labels is None:
        labels = np.unique(np.concatenate([a, b]))
    labels = np.asarray(sorted(labels), dtype=float)
    k = len(labels)
    index = {v: i for i, v in enumerate(labels)}

    o = np.zeros((k, k))
    for x, y in zip(a, b):
        o[index[x], index[y]] += 1
    if o.sum() == 0:
        return np.nan

    expected = np.outer(o.sum(axis=1), o.sum(axis=0)) / o.sum()
    gaps = np.arange(k)[:, None] - np.arange(k)[None, :]
    weights = (gaps / (k - 1)) ** 2 if k > 1 else np.zeros((k, k))

    denom = np.sum(weights * expected)
    if denom == 0:
        return 1.0
    return 1.0 - np.sum(weights * o) / denom


def icc(matrix, form="2,1"):
    """双向 ANOVA 均方分解计算 ICC。matrix 形如 (n_subjects, n_raters)。

    form="2,1": two-way random, absolute agreement, single rater
    form="3,1": two-way mixed, consistency, single rater
    """
    x = np.asarray(matrix, dtype=float)
    x = x[~np.isnan(x).any(axis=1)]
    n, k = x.shape
    if n < 2 or k < 2:
        return np.nan

    grand = x.mean()
    row_mean = x.mean(axis=1)
    col_mean = x.mean(axis=0)

    ss_rows = k * np.sum((row_mean - grand) ** 2)
    ss_cols = n * np.sum((col_mean - grand) ** 2)
    ss_total = np.sum((x - grand) ** 2)
    ss_error = ss_total - ss_rows - ss_cols

    msr = ss_rows / (n - 1)
    msc = ss_cols / (k - 1)
    mse = ss_error / ((n - 1) * (k - 1))
    if mse <= 0:
        return 1.0

    if form == "2,1":
        denom = msr + (k - 1) * mse + k * (msc - mse) / n
    elif form == "3,1":
        denom = msr + (k - 1) * mse
    else:
        raise ValueError(f"不支持的 ICC 形式：{form}")
    return (msr - mse) / denom if denom else np.nan


def agreement_block(a, b, labels=None):
    """一组完整的一致性指标。"""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    mask = ~(np.isnan(a) | np.isnan(b))
    a, b = a[mask], b[mask]
    if len(a) < 2:
        return {"n": len(a)}

    diff = a - b
    pearson = stats.pearsonr(a, b)[0] if np.std(a) and np.std(b) else np.nan
    return {
        "n": len(a),
        "QWK": quadratic_weighted_kappa(a, b, labels),
        "ICC_2_1": icc(np.column_stack([a, b]), "2,1"),
        "ICC_3_1": icc(np.column_stack([a, b]), "3,1"),
        "Pearson_r": pearson,
        "Spearman_rho": stats.spearmanr(a, b)[0],
        "MAE": float(np.mean(np.abs(diff))),
        "RMSE": float(np.sqrt(np.mean(diff ** 2))),
        "mean_bias": float(np.mean(diff)),
        "SD_bias": float(np.std(diff, ddof=1)),
        "exact_agreement": float(np.mean(np.abs(diff) < 1e-9)),
        "within_0.5": float(np.mean(np.abs(diff) <= 0.5)),
        "within_1": float(np.mean(np.abs(diff) <= 1.0)),
        "within_2": float(np.mean(np.abs(diff) <= 2.0)),
    }


def bootstrap_ci(a, b, fn, n_boot=1000, alpha=0.05, seed=42):
    """对任意 (a, b) -> scalar 的指标做 bootstrap 置信区间。"""
    rng = np.random.default_rng(seed)
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    mask = ~(np.isnan(a) | np.isnan(b))
    a, b = a[mask], b[mask]
    n = len(a)
    if n < 10:
        return (np.nan, np.nan)

    values = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        try:
            value = fn(a[idx], b[idx])
        except Exception:
            continue
        if value is not None and np.isfinite(value):
            values.append(value)
    if len(values) < 50:
        return (np.nan, np.nan)
    lo, hi = np.percentile(values, [alpha / 2 * 100, (1 - alpha / 2) * 100])
    return float(lo), float(hi)


def to_grade(score, max_score):
    """按得分率转五级制，用于等级一致性分析。"""
    ratio = score / max_score if max_score else np.nan
    if np.isnan(ratio):
        return ""
    for cut, grade in ((0.9, "A"), (0.8, "B"), (0.7, "C"), (0.6, "D")):
        if ratio >= cut:
            return grade
    return "F"


GRADE_ORDER = ["F", "D", "C", "B", "A"]


# --------------------------------------------------------------------------
# 分析主体
# --------------------------------------------------------------------------
def build_wide(df, left="ai_score", right="teacher_score"):
    return df[["answer_pid", "question_id", left, right]].rename(
        columns={left: "a", right: "b"}
    )


def human_baseline(df):
    """教师之间的基线一致性（需要 teacher_id 且同一题被两位教师评过）。"""
    if "teacher_id" not in df.columns:
        return None
    piv = df.pivot_table(
        index=["answer_pid", "question_id"], columns="teacher_id",
        values="teacher_score", aggfunc="mean",
    ).dropna()
    if piv.shape[1] < 2:
        return None
    cols = list(piv.columns)
    rows = [{"pair": f"{cols[0]} vs {cols[1]}",
             **agreement_block(piv[cols[0]].values, piv[cols[1]].values)}]
    return pd.DataFrame(rows)


def main_metrics(df):
    block = agreement_block(df["ai_score"], df["teacher_score"])
    ci_qwk = bootstrap_ci(
        df["ai_score"], df["teacher_score"], quadratic_weighted_kappa
    )
    ci_icc = bootstrap_ci(
        df["ai_score"], df["teacher_score"],
        lambda a, b: icc(np.column_stack([a, b]), "2,1"),
    )
    block["QWK_CI95"] = f"[{ci_qwk[0]:.3f}, {ci_qwk[1]:.3f}]"
    block["ICC_2_1_CI95"] = f"[{ci_icc[0]:.3f}, {ci_icc[1]:.3f}]"
    return block


def grade_metrics(df):
    if "max_score" not in df.columns:
        return None
    g_ai = [to_grade(s, m) for s, m in zip(df["ai_score"], df["max_score"])]
    g_te = [to_grade(s, m) for s, m in zip(df["teacher_score"], df["max_score"])]
    return {
        **agreement_block(
            [GRADE_ORDER.index(g) for g in g_ai],
            [GRADE_ORDER.index(g) for g in g_te],
            labels=list(range(len(GRADE_ORDER))),
        ),
        "grade_exact_agreement": float(np.mean([x == y for x, y in zip(g_ai, g_te)])),
    }


def stratified(df, by):
    if by not in df.columns:
        return pd.DataFrame()
    rows = []
    for value, group in df.groupby(by):
        if len(group) < 10:
            continue
        rows.append({by: value, **agreement_block(group["ai_score"], group["teacher_score"])})
    return pd.DataFrame(rows)


def centrality(df):
    """趋中效应：teacher ~ ai 回归斜率 < 1 说明 AI 分数向均值收缩。"""
    mask = df["ai_score"].notna() & df["teacher_score"].notna()
    x = df.loc[mask, "ai_score"].astype(float)
    y = df.loc[mask, "teacher_score"].astype(float)
    if len(x) < 10 or x.std() == 0:
        return {}
    res = stats.linregress(x, y)
    # 检验 H0: slope = 1（而非 linregress 默认的 slope = 0）
    t_stat = (res.slope - 1.0) / res.stderr if res.stderr else np.nan
    p_vs_1 = 2 * (1 - stats.t.cdf(abs(t_stat), df=len(x) - 2))
    return {
        "slope": res.slope,
        "slope_stderr": res.stderr,
        "intercept": res.intercept,
        "r_squared": res.rvalue ** 2,
        "slope_p_vs_1": float(p_vs_1),
        "note": "斜率显著小于 1 表示 AI 评分存在向均值回归的趋中倾向",
    }


def hitl_metrics(df):
    """人在回路：修正率、修正幅度、修正后一致性。"""
    if "final_score" not in df.columns:
        return None, None
    d = df[df["final_score"].notna()].copy()
    if d.empty:
        return None, None
    d["is_edited"] = (d["final_score"] - d["ai_score"]).abs() > 1e-9
    d["edit_delta"] = d["final_score"] - d["ai_score"]

    summary = {
        "n_final": len(d),
        "adoption_rate": float(1 - d["is_edited"].mean()),
        "revision_rate": float(d["is_edited"].mean()),
        "mean_abs_delta": float(d.loc[d["is_edited"], "edit_delta"].abs().mean())
        if d["is_edited"].any() else 0.0,
        "p90_abs_delta": float(np.percentile(d.loc[d["is_edited"], "edit_delta"].abs(), 90))
        if d["is_edited"].any() else 0.0,
        "max_abs_delta": float(d["edit_delta"].abs().max()),
        "share_teacher_added": float((d["edit_delta"] > 0).mean()),
        "share_teacher_deducted": float((d["edit_delta"] < 0).mean()),
        "share_large_revision_ge2": float((d["edit_delta"].abs() >= 2).mean()),
        "post_hoc_QWK": quadratic_weighted_kappa(d["final_score"], d["teacher_score"]),
        "post_hoc_MAE": float(np.mean(np.abs(d["final_score"] - d["teacher_score"]))),
    }
    by_type = None
    if "question_type" in d.columns:
        rows = []
        for qtype, group in d.groupby("question_type", observed=True):
            rows.append({
                "question_type": qtype,
                "n": len(group),
                "revision_rate": float(group["is_edited"].mean()),
                "mean_abs_delta": float(group["edit_delta"].abs().mean()),
                "share_teacher_added": float((group["edit_delta"] > 0).mean()),
                "share_large_revision_ge2": float(
                    (group["edit_delta"].abs() >= 2).mean()
                ),
            })
        by_type = pd.DataFrame(rows)
    return summary, by_type


def efficiency(df):
    """人力时间：纯人工批改 vs 审核 AI 建议。"""
    cols = {"teacher_time_ms", "review_time_ms"}
    if not cols.issubset(df.columns):
        return None
    d = df[["teacher_time_ms", "review_time_ms"]].dropna()
    if len(d) < 5:
        return None
    manual = d["teacher_time_ms"].astype(float) / 1000.0
    review = d["review_time_ms"].astype(float) / 1000.0
    diff = manual - review

    normal = stats.shapiro(diff)[1] > 0.05 if 3 < len(diff) <= 5000 else False
    if normal:
        stat, p = stats.ttest_rel(manual, review)
        test = f"配对 t 检验 t={stat:.3f}"
    else:
        stat, p = stats.wilcoxon(manual, review)
        test = f"Wilcoxon 符号秩 W={stat:.3f}"

    cohens_d = float(diff.mean() / diff.std(ddof=1)) if diff.std(ddof=1) else np.nan
    return {
        "n": len(d),
        "manual_mean_s": float(manual.mean()),
        "manual_sd_s": float(manual.std(ddof=1)),
        "review_mean_s": float(review.mean()),
        "review_sd_s": float(review.std(ddof=1)),
        "saved_mean_s": float(diff.mean()),
        "saved_pct": float(diff.mean() / manual.mean() * 100),
        "test": test,
        "p_value": float(p),
        "cohens_d": cohens_d,
        "normality_shapiro_p": float(stats.shapiro(diff)[1]) if 3 < len(diff) <= 5000 else np.nan,
    }


def retest_reliability(df):
    """AI 重测信度：同题跑两次的稳定性。"""
    if "ai_attempt" not in df.columns:
        return None
    piv = df.pivot_table(
        index=["answer_pid", "question_id"], columns="ai_attempt",
        values="ai_score", aggfunc="mean",
    ).dropna()
    if piv.shape[1] < 2:
        return None
    cols = sorted(piv.columns)[:2]
    return agreement_block(piv[cols[0]].values, piv[cols[1]].values)


# --------------------------------------------------------------------------
# 绘图
# --------------------------------------------------------------------------
def make_figures(df, outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    x = df["ai_score"].astype(float)
    y = df["teacher_score"].astype(float)

    fig, ax = plt.subplots(figsize=(5, 4.5))
    ax.scatter(x, y, s=14, alpha=0.45, color="#378ADD", edgecolors="none")
    lim = [min(x.min(), y.min()) - 1, max(x.max(), y.max()) + 1]
    ax.plot(lim, lim, "--", color="#888780", lw=1, label="y = x")
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("AI 评分"); ax.set_ylabel("教师评分"); ax.legend()
    ax.set_title("AI 评分与教师评分散点图")
    fig.tight_layout(); fig.savefig(outdir / "fig1_scatter.png", dpi=160); plt.close(fig)

    mean_xy = (x + y) / 2
    diff_xy = x - y
    md, sd = diff_xy.mean(), diff_xy.std(ddof=1)
    fig, ax = plt.subplots(figsize=(5, 4.5))
    ax.scatter(mean_xy, diff_xy, s=14, alpha=0.45, color="#D85A30", edgecolors="none")
    ax.axhline(md, color="#185FA5", lw=1.2, label=f"均值偏差 {md:.2f}")
    ax.axhline(md + 1.96 * sd, color="#888780", ls="--", lw=1, label=f"+1.96SD {md + 1.96 * sd:.2f}")
    ax.axhline(md - 1.96 * sd, color="#888780", ls="--", lw=1, label=f"-1.96SD {md - 1.96 * sd:.2f}")
    ax.set_xlabel("(AI 分 + 教师分) / 2"); ax.set_ylabel("AI 分 - 教师分")
    ax.legend(fontsize=9); ax.set_title("Bland-Altman 图")
    fig.tight_layout(); fig.savefig(outdir / "fig2_bland_altman.png", dpi=160); plt.close(fig)

    fig, ax = plt.subplots(figsize=(5, 4))
    ax.hist(diff_xy, bins=np.arange(np.floor(diff_xy.min()) - 0.25, np.ceil(diff_xy.max()) + 0.75, 0.5),
            color="#7F77DD", alpha=0.85)
    ax.axvline(0, color="#5F5E5A", lw=1)
    ax.set_xlabel("AI 分 - 教师分"); ax.set_ylabel("题-卷样本数")
    ax.set_title("评分误差分布")
    fig.tight_layout(); fig.savefig(outdir / "fig3_error_hist.png", dpi=160); plt.close(fig)

    if "final_score" in df.columns and df["final_score"].notna().any():
        delta = (df["final_score"].astype(float) - x).dropna()
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.hist(delta, bins=30, color="#1D9E75", alpha=0.85)
        ax.axvline(0, color="#5F5E5A", lw=1)
        ax.set_xlabel("最终分 - AI 建议分"); ax.set_ylabel("题-卷样本数")
        ax.set_title("教师修正幅度分布")
        fig.tight_layout(); fig.savefig(outdir / "fig4_edit_delta.png", dpi=160); plt.close(fig)

    if {"teacher_time_ms", "review_time_ms"}.issubset(df.columns):
        d = df[["teacher_time_ms", "review_time_ms"]].dropna()
        if not d.empty:
            fig, ax = plt.subplots(figsize=(4.5, 4))
            ax.boxplot([d["teacher_time_ms"] / 1000, d["review_time_ms"] / 1000],
                       labels=["人工批改", "AI 建议审核"])
            ax.set_ylabel("耗时（秒）"); ax.set_title("单题批改耗时对比")
            fig.tight_layout(); fig.savefig(outdir / "fig5_time.png", dpi=160); plt.close(fig)


# --------------------------------------------------------------------------
def demo_data(n_papers=120, seed=7):
    rng = np.random.default_rng(seed)
    types = ["简答题", "计算题", "证明题"]
    rows = []
    for p in range(n_papers):
        for q, qtype in enumerate(types, 1):
            max_score = {"简答题": 10.0, "计算题": 15.0, "证明题": 20.0}[qtype]
            true_ability = rng.beta(5, 2)
            teacher = np.clip(rng.normal(true_ability * max_score, max_score * 0.06), 0, max_score)
            teacher = round(teacher * 2) / 2
            noise = {"简答题": 0.09, "计算题": 0.13, "证明题": 0.17}[qtype] * max_score
            ai = np.clip(rng.normal(teacher + 0.25, noise), 0, max_score)
            ai = round(ai * 2) / 2
            final = ai if rng.random() > 0.32 else round(np.clip(ai + rng.choice([-1, 1, 0.5, 2]), 0, max_score) * 2) / 2
            rows.append({
                "answer_pid": f"A{p:04d}", "question_id": f"Q{q}",
                "question_type": qtype, "max_score": max_score,
                "ai_score": ai, "teacher_score": teacher, "final_score": final,
                "teacher_time_ms": float(rng.normal(38, 9) * 1000),
                "review_time_ms": float(rng.normal(17, 5) * 1000),
                "ai_latency_ms": float(rng.normal(3200, 700)),
            })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", help="grading_study.csv 路径")
    parser.add_argument("--outdir", default="out")
    args = parser.parse_args()

    if args.csv:
        df = pd.read_csv(args.csv)
        missing = [c for c in REQUIRED if c not in df.columns]
        if missing:
            sys.exit(f"缺少必需列：{missing}")
    else:
        df = demo_data()
        print("未指定 --csv，使用合成演示数据（仅用于验证脚本）\n")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    report = {}

    print("=" * 62)
    print("RQ1  整体一致性")
    print("=" * 62)
    report["RQ1_overall"] = main_metrics(df)
    for key, value in report["RQ1_overall"].items():
        print(f"  {key:<22} {value if isinstance(value, str) else round(value, 4)}")

    print("\n" + "=" * 62)
    print("RQ1b 等级一致性（A/B/C/D/F）")
    print("=" * 62)
    report["RQ1_grade"] = grade_metrics(df)
    if report["RQ1_grade"]:
        for key, value in report["RQ1_grade"].items():
            print(f"  {key:<22} {round(value, 4) if isinstance(value, float) else value}")

    baseline = human_baseline(df)
    if baseline is not None:
        print("\n" + "=" * 62)
        print("人类基线（教师之间的一致性）——论文最重要的对比")
        print("=" * 62)
        print(baseline.to_string(index=False))
        baseline.to_csv(outdir / "table_human_baseline.csv", index=False)

    print("\n" + "=" * 62)
    print("RQ2  分层一致性（按题型 / 得分率）")
    print("=" * 62)
    by_type = stratified(df, "question_type")
    if not by_type.empty:
        print(by_type.round(4).to_string(index=False))
        by_type.to_csv(outdir / "table_by_question_type.csv", index=False)

    df = df.copy()
    if "max_score" in df.columns:
        df["band"] = pd.cut(df["teacher_score"] / df["max_score"],
                            [0, 0.4, 0.7, 1.01], labels=["低分档", "中分档", "高分档"])
        by_band = stratified(df, "band")
        if not by_band.empty:
            print()
            print(by_band.round(4).to_string(index=False))
            by_band.to_csv(outdir / "table_by_score_band.csv", index=False)

    print("\n趋中效应检验")
    cen = centrality(df)
    for key, value in cen.items():
        print(f"  {key:<16} {round(value, 4) if isinstance(value, float) else value}")

    retest = retest_reliability(df)
    if retest:
        print("\nAI 重测信度（同题两次评分）")
        for key, value in retest.items():
            print(f"  {key:<16} {round(value, 4) if isinstance(value, float) else value}")
        report["retest"] = retest

    print("\n" + "=" * 62)
    print("RQ3  人在回路")
    print("=" * 62)
    hitl, hitl_by_type = hitl_metrics(df)
    if hitl:
        for key, value in hitl.items():
            print(f"  {key:<24} {round(value, 4) if isinstance(value, float) else value}")
        report["RQ3_hitl"] = hitl
        if hitl_by_type is not None:
            print()
            print(hitl_by_type.round(4).to_string(index=False))
            hitl_by_type.to_csv(outdir / "table_revision_by_type.csv", index=False)

    print("\n" + "=" * 62)
    print("RQ4  效率对比（人力时间）")
    print("=" * 62)
    eff = efficiency(df)
    if eff:
        for key, value in eff.items():
            print(f"  {key:<20} {round(value, 4) if isinstance(value, float) else value}")
        report["RQ4_efficiency"] = eff

    make_figures(df, outdir)
    (outdir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"\n图表已输出到 {outdir.resolve()}，汇总见 report.json")


if __name__ == "__main__":
    main()
