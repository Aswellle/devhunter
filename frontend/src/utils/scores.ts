/**
 * 推荐徽标的统一分数阈值。
 * ForYouSection 与 RecommendPage 曾各自硬编码（70 / 80）导致同一分数两处含义不同，
 * 现统一为 80：推荐页全量列表与首页"为你推荐"使用同一口径。
 */
export const RECOMMENDED_BADGE_SCORE = 80
