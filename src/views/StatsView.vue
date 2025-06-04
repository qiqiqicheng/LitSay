<template>
  <div class="stats-container">
    <a-row :gutter="16">
      <a-col :span="24">
        <a-page-header
          title="统计分析"
          sub-title="文献管理系统数据概览"
          :backIcon="false"
        />
      </a-col>
    </a-row>

    <!-- 加载状态 -->
    <a-spin :spinning="loading" tip="数据加载中...">
      <!-- 基本数据统计卡片 -->
      <a-row :gutter="16" style="margin-bottom: 16px">
        <a-col :xs="24" :sm="8">
          <a-card hoverable>
            <template #cover>
              <div
                class="stats-card-icon-wrapper"
                style="background-color: #e6f7ff"
              >
                <book-outlined class="stats-card-icon" style="color: #1890ff" />
              </div>
            </template>
            <a-card-meta title="文献总数">
              <template #description>
                <div class="stats-number">
                  {{ overviewData.documentsCount }}
                </div>
              </template>
            </a-card-meta>
          </a-card>
        </a-col>

        <a-col :xs="24" :sm="8">
          <a-card hoverable>
            <template #cover>
              <div
                class="stats-card-icon-wrapper"
                style="background-color: #f6ffed"
              >
                <folder-outlined
                  class="stats-card-icon"
                  style="color: #52c41a"
                />
              </div>
            </template>
            <a-card-meta title="文件夹数量">
              <template #description>
                <div class="stats-number">{{ overviewData.foldersCount }}</div>
              </template>
            </a-card-meta>
          </a-card>
        </a-col>

        <a-col :xs="24" :sm="8">
          <a-card hoverable>
            <template #cover>
              <div
                class="stats-card-icon-wrapper"
                style="background-color: #fff2e8"
              >
                <user-outlined class="stats-card-icon" style="color: #fa8c16" />
              </div>
            </template>
            <a-card-meta title="收录作者数量">
              <template #description>
                <div class="stats-number">{{ overviewData.authorsCount }}</div>
              </template>
            </a-card-meta>
          </a-card>
        </a-col>
      </a-row>

      <!-- 关键词统计图表 -->
      <a-row :gutter="16" style="margin-bottom: 16px">
        <a-col :span="24">
          <a-card title="关键词文献数量 TOP 5" :loading="loading">
            <template #extra> <tag-outlined /> 关键词分析 </template>
            <div ref="keywordsChartContainer" style="height: 400px"></div>
          </a-card>
        </a-col>
      </a-row>

      <!-- 作者星级统计图表 -->
      <a-row :gutter="16">
        <a-col :span="24">
          <a-card title="作者星级评分 TOP 5" :loading="loading">
            <template #extra> <star-outlined /> 星级分析 </template>
            <div ref="authorsChartContainer" style="height: 400px"></div>
          </a-card>
        </a-col>
      </a-row>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import {
  BookOutlined,
  FolderOutlined,
  UserOutlined,
  TagOutlined,
  StarOutlined,
} from "@ant-design/icons-vue";
import {
  getStatsOverview,
  getKeywordsTop,
  getAuthorsStarsTop,
  getMockStatsData,
} from "@/api/stats";
import * as echarts from "echarts/core";
import { BarChart, BarSeriesOption } from "echarts/charts";
import {
  TitleComponent,
  TitleComponentOption,
  TooltipComponent,
  TooltipComponentOption,
  GridComponent,
  GridComponentOption,
  LegendComponent,
  LegendComponentOption,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

// 注册必须的组件
echarts.use([
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  BarChart,
  CanvasRenderer,
]);

type ECOption = echarts.ComposeOption<
  | BarSeriesOption
  | TitleComponentOption
  | TooltipComponentOption
  | GridComponentOption
  | LegendComponentOption
>;

// 状态变量
const loading = ref(true);
const overviewData = ref({
  documentsCount: 0,
  foldersCount: 0,
  authorsCount: 0,
});
const keywordsTop = ref<Array<{ keyword: string; count: number }>>([]);
const authorsStarsTop = ref<Array<{ author: string; stars: number }>>([]);

// Chart refs
const keywordsChartContainer = ref<HTMLElement | null>(null);
const authorsChartContainer = ref<HTMLElement | null>(null);
let keywordsChart: echarts.ECharts | null = null;
let authorsChart: echarts.ECharts | null = null;

// 获取统计数据
const fetchStatsData = async () => {
  try {
    loading.value = true;

    // 是否使用模拟数据 - 实际项目中可根据环境变量或其他条件判断
    const useMockData = true;

    if (useMockData) {
      // 使用模拟数据
      const mockData = getMockStatsData();
      overviewData.value = mockData.overview;
      keywordsTop.value = mockData.keywordsTop;
      authorsStarsTop.value = mockData.authorsStarsTop;
    } else {
      // 并行请求多个数据
      const [overviewResp, keywordsResp, authorsResp] = await Promise.all([
        getStatsOverview(),
        getKeywordsTop(),
        getAuthorsStarsTop(),
      ]);

      overviewData.value = overviewResp.data;
      keywordsTop.value = keywordsResp.data;
      authorsStarsTop.value = authorsResp.data;
    }

    // 初始化图表
    initCharts();
  } catch (error) {
    console.error("获取统计数据失败:", error);
  } finally {
    loading.value = false;
  }
};

// 初始化图表
const initCharts = () => {
  // 确保DOM元素已经挂载
  if (!keywordsChartContainer.value || !authorsChartContainer.value) {
    return;
  }

  // 初始化关键词图表
  keywordsChart = echarts.init(keywordsChartContainer.value);
  const keywordsOption: ECOption = {
    title: {
      text: "关键词文献分布",
      subtext: "基于文献关键词统计",
      left: "center",
    },
    tooltip: {
      trigger: "axis",
      axisPointer: {
        type: "shadow",
      },
      formatter: "{b}: {c} 篇文献",
    },
    grid: {
      left: "3%",
      right: "4%",
      bottom: "3%",
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: keywordsTop.value.map((item) => item.keyword),
      axisTick: {
        alignWithLabel: true,
      },
      axisLabel: {
        rotate: 45,
        interval: 0,
      },
    },
    yAxis: {
      type: "value",
      name: "文献数量",
    },
    series: [
      {
        name: "文献数量",
        type: "bar",
        barWidth: "60%",
        data: keywordsTop.value.map((item) => item.count),
        itemStyle: {
          color: "#1890ff",
        },
        label: {
          show: true,
          position: "top",
          formatter: "{c}",
        },
        emphasis: {
          itemStyle: {
            color: "#40a9ff",
          },
        },
      },
    ],
  };
  keywordsChart.setOption(keywordsOption);

  // 初始化作者星级图表
  authorsChart = echarts.init(authorsChartContainer.value);
  const authorsOption: ECOption = {
    title: {
      text: "作者星级评分",
      subtext: "基于用户对文献的评分",
      left: "center",
    },
    tooltip: {
      trigger: "axis",
      axisPointer: {
        type: "shadow",
      },
      formatter: "{b}: {c} 星",
    },
    grid: {
      left: "3%",
      right: "4%",
      bottom: "3%",
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: authorsStarsTop.value.map((item) => item.author),
      axisTick: {
        alignWithLabel: true,
      },
    },
    yAxis: {
      type: "value",
      name: "星级总数",
    },
    series: [
      {
        name: "星级评分",
        type: "bar",
        barWidth: "60%",
        data: authorsStarsTop.value.map((item) => item.stars),
        itemStyle: {
          color: "#fa8c16", // 使用不同颜色区分
        },
        label: {
          show: true,
          position: "top",
          formatter: "{c}",
        },
        emphasis: {
          itemStyle: {
            color: "#ffa940",
          },
        },
      },
    ],
  };
  authorsChart.setOption(authorsOption);
};

// 窗口大小变化时调整图表大小
const handleResize = () => {
  keywordsChart?.resize();
  authorsChart?.resize();
};

onMounted(() => {
  fetchStatsData();
  window.addEventListener("resize", handleResize);
});

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
  keywordsChart?.dispose();
  authorsChart?.dispose();
});
</script>

<style scoped>
.stats-container {
  padding: 16px;
}

.stats-card-icon-wrapper {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 120px;
  border-radius: 2px 2px 0 0;
  padding: 24px;
}

.stats-card-icon {
  font-size: 64px;
}

.stats-number {
  font-size: 36px;
  font-weight: 600;
  color: #262626;
  line-height: 1.2;
  margin-top: 8px;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .stats-number {
    font-size: 28px;
  }

  .stats-card-icon {
    font-size: 48px;
  }

  .stats-card-icon-wrapper {
    height: 100px;
  }
}
</style>
