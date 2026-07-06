import {
  BgColorsOutlined,
  LayoutOutlined,
  MailOutlined,
  PlayCircleOutlined,
  RocketOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from '@ant-design/icons';
import React from 'react';
import AnimatedLayout from '../components/shared/AnimatedLayout';
import GlassCard from '../components/shared/GlassCard';
import NeumorphicButton from '../components/shared/NeumorphicButton';
import PremiumInput from '../components/shared/PremiumInput';

const DesignSystem: React.FC = () => {
  return (
    <AnimatedLayout>
      <div className="max-w-6xl mx-auto px-6 py-12 space-y-16">
        {/* Header */}
        <section className="space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent-primary/10 text-accent-primary border border-accent-primary/20 text-xs font-bold uppercase tracking-wider">
            <ThunderboltOutlined /> Design System 2.0
          </div>
          <h1 className="text-4xl md:text-5xl font-bold text-text-primary tracking-tight">
            视觉语言与交互规范
          </h1>
          <p className="text-lg text-text-secondary max-w-2xl">
            基于玻璃拟态 (Glassmorphism)、微质感 (Micro-textures) 与编辑主义 (Editorial)
            的全面升级， 旨在为 AI 微调平台提供极致的视觉高级感与交互性能。
          </p>
        </section>

        {/* 玻璃拟态展示 */}
        <section className="space-y-8">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-bg-elevated flex items-center justify-center border border-surface-border">
              <LayoutOutlined className="text-accent-primary" />
            </div>
            <h2 className="text-2xl font-bold text-text-primary">
              玻璃拟态 & 材质 (Glassmorphism)
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <GlassCard intensity="low">
              <div className="space-y-3">
                <h3 className="font-bold text-lg">Low Intensity</h3>
                <p className="text-text-secondary text-sm">
                  更通透的磨砂感，适合背景较复杂或作为次要层级的容器。
                </p>
                <div className="pt-4 flex gap-2">
                  <div className="w-12 h-12 rounded-full bg-accent-primary/20 animate-pulse" />
                  <div className="w-12 h-12 rounded-full bg-accent-secondary/20 animate-pulse delay-75" />
                </div>
              </div>
            </GlassCard>

            <GlassCard intensity="medium">
              <div className="space-y-3">
                <h3 className="font-bold text-lg">Medium Intensity</h3>
                <p className="text-text-secondary text-sm">
                  标准的玻璃拟态效果，具备反射层与微质感噪声，推荐作为主卡片使用。
                </p>
                <NeumorphicButton size="sm">探索更多</NeumorphicButton>
              </div>
            </GlassCard>

            <GlassCard intensity="high">
              <div className="space-y-3">
                <h3 className="font-bold text-lg">High Intensity</h3>
                <p className="text-text-secondary text-sm">
                  高饱和度、高模糊度的质感，提供最强的景深效果与视觉重心。
                </p>
                <div className="h-2 w-full bg-bg-hover rounded-full overflow-hidden">
                  <div className="h-full w-2/3 bg-accent-primary rounded-full shadow-[0_0_8px_var(--accent-primary)]" />
                </div>
              </div>
            </GlassCard>
          </div>
        </section>

        {/* 交互组件展示 */}
        <section className="space-y-8">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-bg-elevated flex items-center justify-center border border-surface-border">
              <PlayCircleOutlined className="text-accent-primary" />
            </div>
            <h2 className="text-2xl font-bold text-text-primary">交互反馈 (Interaction)</h2>
          </div>

          <GlassCard>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
              <div className="space-y-6">
                <h4 className="text-sm font-bold uppercase tracking-widest text-text-tertiary">
                  物理按压按钮
                </h4>
                <div className="flex flex-wrap gap-4">
                  <NeumorphicButton variant="primary">
                    <RocketOutlined /> 启动训练
                  </NeumorphicButton>
                  <NeumorphicButton variant="secondary">取消操作</NeumorphicButton>
                  <NeumorphicButton variant="danger">删除数据</NeumorphicButton>
                  <NeumorphicButton variant="ghost">幽灵按钮</NeumorphicButton>
                </div>
                <div className="flex flex-wrap items-center gap-4">
                  <NeumorphicButton size="sm">Small</NeumorphicButton>
                  <NeumorphicButton size="md">Medium</NeumorphicButton>
                  <NeumorphicButton size="lg">Large Size</NeumorphicButton>
                </div>
              </div>

              <div className="space-y-6">
                <h4 className="text-sm font-bold uppercase tracking-widest text-text-tertiary">
                  精致表单输入
                </h4>
                <div className="space-y-4">
                  <PremiumInput
                    label="用户名"
                    placeholder="请输入您的姓名"
                    icon={<UserOutlined />}
                  />
                  <PremiumInput
                    label="电子邮箱"
                    placeholder="name@example.com"
                    icon={<MailOutlined />}
                    suffix={<span className="text-[10px] font-bold opacity-50">VERIFIED</span>}
                  />
                  <PremiumInput
                    label="带有错误的输入"
                    placeholder="错误的输入状态..."
                    error="格式不正确，请重新输入"
                  />
                </div>
              </div>
            </div>
          </GlassCard>
        </section>

        {/* 色彩体系 */}
        <section className="space-y-8">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-bg-elevated flex items-center justify-center border border-surface-border">
              <BgColorsOutlined className="text-accent-primary" />
            </div>
            <h2 className="text-2xl font-bold text-text-primary">色彩体系 (Colors)</h2>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: 'Primary Accent', color: 'bg-accent-primary' },
              { label: 'Secondary Accent', color: 'bg-accent-secondary' },
              { label: 'Tertiary Accent', color: 'bg-accent-tertiary' },
              { label: 'Success', color: 'bg-success' },
              { label: 'Warning', color: 'bg-warning' },
              { label: 'Error', color: 'bg-error' },
              { label: 'Info', color: 'bg-info' },
              { label: 'Surface Elevated', color: 'bg-bg-elevated' },
            ].map((item) => (
              <div
                key={item.label}
                className="p-4 rounded-xl bg-bg-secondary border border-surface-border space-y-3"
              >
                <div className={`w-full h-12 rounded-lg ${item.color} shadow-sm`} />
                <span className="text-xs font-bold text-text-secondary">{item.label}</span>
              </div>
            ))}
          </div>
        </section>

        {/* 迁移指南 */}
        <section className="space-y-8">
          <GlassCard intensity="low" className="border-accent-primary/30">
            <div className="flex flex-col md:flex-row gap-8 items-center">
              <div className="flex-1 space-y-4">
                <h2 className="text-2xl font-bold text-text-primary">准备好开始升级了吗？</h2>
                <p className="text-text-secondary">
                  我们已经为您准备好了完整的迁移指南，包括 Tailwind 配置映射、新组件的 API
                  变更以及动效优化建议。
                </p>
                <div className="flex gap-4">
                  <NeumorphicButton variant="primary">查看迁移指南</NeumorphicButton>
                  <NeumorphicButton variant="secondary">下载设计手册</NeumorphicButton>
                </div>
              </div>
              <div className="w-32 h-32 md:w-48 md:h-48 rounded-2xl bg-gradient-to-br from-accent-primary/20 to-accent-secondary/20 flex items-center justify-center border border-accent-primary/10">
                <RocketOutlined className="text-6xl text-accent-primary animate-bounce" />
              </div>
            </div>
          </GlassCard>
        </section>
      </div>
    </AnimatedLayout>
  );
};

export default DesignSystem;
