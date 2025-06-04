import axios from "axios";
import { API_BASE_URL, buildApiPath, getAuthHeaders } from "./config";

/**
 * 获取用户统计数据
 * @returns Promise 包含统计概览数据
 */
export const getStatsOverview = async () => {
  try {
    const response = await axios.get(buildApiPath("/stats/overview"), {
      headers: getAuthHeaders(),
    });
    return response.data;
  } catch (error) {
    console.error("获取统计概览数据失败", error);
    throw error;
  }
};

/**
 * 获取关键词Top5统计
 * @returns Promise 包含关键词统计数据
 */
export const getKeywordsTop = async () => {
  try {
    const response = await axios.get(buildApiPath("/stats/keywords/top"), {
      headers: getAuthHeaders(),
      params: { limit: 5 },
    });
    return response.data;
  } catch (error) {
    console.error("获取关键词统计数据失败", error);
    throw error;
  }
};

/**
 * 获取作者星级Top5统计
 * @returns Promise 包含作者星级统计数据
 */
export const getAuthorsStarsTop = async () => {
  try {
    const response = await axios.get(buildApiPath("/stats/authors/stars"), {
      headers: getAuthHeaders(),
      params: { limit: 5 },
    });
    return response.data;
  } catch (error) {
    console.error("获取作者星级统计数据失败", error);
    throw error;
  }
};

/**
 * 模拟数据：用于开发环境测试
 */
export const getMockStatsData = () => {
  // 基本统计数据
  const overview = {
    documentsCount: 78,
    foldersCount: 14,
    authorsCount: 43,
  };

  // 关键词统计数据
  const keywordsTop = [
    { keyword: "机器学习", count: 24 },
    { keyword: "深度学习", count: 18 },
    { keyword: "计算机视觉", count: 15 },
    { keyword: "自然语言处理", count: 12 },
    { keyword: "强化学习", count: 9 },
  ];

  // 作者星级统计数据
  const authorsStarsTop = [
    { author: "张三", stars: 21 },
    { author: "李四", stars: 18 },
    { author: "王五", stars: 15 },
    { author: "赵六", stars: 13 },
    { author: "孙七", stars: 11 },
  ];

  return {
    overview,
    keywordsTop,
    authorsStarsTop,
  };
};
