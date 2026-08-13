import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  closestCenter,
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

const SORT_TRANSITION = {
  duration: 220,
  easing: "cubic-bezier(0.2, 0.8, 0.2, 1)",
};

function restrictToVerticalAxis({ transform }) {
  return { ...transform, x: 0 };
}

function SortableListItem({ id, item, index, renderItem }) {
  const {
    attributes,
    isDragging,
    isSorting,
    listeners,
    setActivatorNodeRef,
    setNodeRef,
    transform,
    transition,
  } = useSortable({ id, transition: SORT_TRANSITION });

  return renderItem(item, index, {
    containerProps: {
      ref: setNodeRef,
      style: {
        transform: CSS.Transform.toString(transform),
        transition,
      },
    },
    handleProps: {
      ...attributes,
      ...listeners,
      ref: setActivatorNodeRef,
    },
    isDragging,
    isSorting,
  });
}

export function SortableList({
  items,
  getId = (item) => item.id,
  onReorder,
  renderItem,
  renderOverlay,
  label = "リスト",
}) {
  const [activeId, setActiveId] = useState(null);
  const ids = useMemo(() => items.map((item) => getId(item)), [getId, items]);
  const activeIndex = activeId == null ? -1 : ids.indexOf(activeId);
  const activeItem = activeIndex >= 0 ? items[activeIndex] : null;
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const finishDrag = () => {
    setActiveId(null);
    window.setTimeout(() => document.body.classList.remove("studio-sorting"), 0);
  };

  useEffect(() => () => document.body.classList.remove("studio-sorting"), []);

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      modifiers={[restrictToVerticalAxis]}
      onDragStart={({ active }) => {
        document.body.classList.add("studio-sorting");
        setActiveId(active.id);
      }}
      onDragCancel={finishDrag}
      onDragEnd={({ active, over }) => {
        finishDrag();
        if (!over || active.id === over.id) return;
        const from = ids.indexOf(active.id);
        const to = ids.indexOf(over.id);
        if (from >= 0 && to >= 0) onReorder(arrayMove(items, from, to));
      }}
      accessibility={{
        screenReaderInstructions: {
          draggable: `${label}の項目を移動するには、スペースキーを押してから上下矢印キーを使い、もう一度スペースキーで確定します。Escapeで中止します。`,
        },
      }}
    >
      <SortableContext items={ids} strategy={verticalListSortingStrategy}>
        {items.map((item, index) => (
          <SortableListItem
            key={getId(item)}
            id={getId(item)}
            item={item}
            index={index}
            renderItem={renderItem}
          />
        ))}
      </SortableContext>
      {createPortal(
        <DragOverlay
          adjustScale={false}
          zIndex={1000}
          dropAnimation={{
            duration: 190,
            easing: "cubic-bezier(0.2, 0.8, 0.2, 1)",
          }}
          className="sortable-drag-overlay"
        >
          {activeItem ? renderOverlay(activeItem, activeIndex) : null}
        </DragOverlay>,
        document.body,
      )}
    </DndContext>
  );
}
