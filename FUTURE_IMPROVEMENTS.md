# 未来实施任务（架构重构）

> 本文档记录需要架构重构的开发任务，建议在功能稳定后实施。

---

## 1. 删除撤销机制

**文件：** `frontend/src/pages/ItemsPage.tsx`

**问题描述：**
当前批量删除操作不可逆，用户误删后无法恢复。

**需求分析：**
- 删除操作前缓存被删条目
- 显示带"撤销"按钮的通知条
- 撤销后恢复条目到列表

**技术方案：**

### 后端需求
```
POST /items/batch-restore
Body: { ids: string[] }
Response: { restored: number }
```

### 前端实现
```typescript
// 1. 创建撤销栈 Hook
function useUndoStack<T>() => {
  stack: T[],
  push: (item: T) => void,
  pop: () => T | undefined,
  clear: () => void,
}

// 2. 删除前缓存
const handleDelete = async (ids: string[]) => {
  const deletedItems = data.items.filter(i => ids.includes(i.id))
  undoStack.push({ type: 'delete', items: deletedItems })
  showUndoSnackbar()
}

// 3. 撤销恢复
const handleUndo = async () => {
  const action = undoStack.pop()
  if (action?.type === 'delete') {
    await itemsApi.batchRestore(action.items.map(i => i.id))
  }
}
```

### UI 组件
- 使用 `react-hot-toast` 的 `toast.custom` 渲染带操作按钮的通知
- 5 秒超时自动消失
- 显示"已删除 N 条 [撤销]"文案

**预估工作量：** 2-3 天

---

## 2. CloudPage 虚拟化渲染

**文件：** `frontend/src/pages/CloudPage.tsx`

**问题描述：**
当前 500 条数据全部渲染到 DOM，低端设备可能出现卡顿。

**需求分析：**
- 只渲染视口内可见条目 + 缓冲区
- 支持平滑滚动
- 保持现有瀑布流布局

**技术方案：**

### 方案 A：@tanstack/react-virtual（推荐）

```typescript
import { useVirtualizer } from '@tanstack/react-virtual'

function CloudPage({ items }) {
  const parentRef = useRef<HTMLDivElement>(null)
  
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 100, // 预估条目高度
    overscan: 5, // 上下各多渲染 5 条
  })

  return (
    <div ref={parentRef} className="h-full overflow-auto">
      <div style={{ height: virtualizer.getTotalSize() }}>
        {virtualizer.getVirtualItems().map(virtualRow => (
          <div
            key={virtualRow.key}
            style={{
              position: 'absolute',
              top: virtualRow.start,
              width: '100%',
            }}
          >
            <CloudItem item={items[virtualRow.index]} />
          </div>
        ))}
      </div>
    </div>
  )
}
```

### 方案 B：react-window

```typescript
import { FixedSizeList } from 'react-window'

// 需要配合 react-window 的 Grid 组件实现瀑布流
```

### CSS 优化（已完成）
- 已添加 `content-visibility: auto`
- 已添加 `contain-intrinsic-size: 0 200px`

**安装依赖：**
```bash
npm install @tanstack/react-virtual
```

**预估工作量：** 1 天

---

## 实施顺序建议

1. **CloudPage 虚拟化**（优先级高，用户体验明显改善）
2. **删除撤销机制**（优先级中等，需后端配合）

---

*文档创建时间：2026-09-17*
