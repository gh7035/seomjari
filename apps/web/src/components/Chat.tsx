// TODO: /api/chat 연동 (직전 진단 컨텍스트를 이어서 후속 질문)
export default function Chat({ disabled }: { disabled: boolean }) {
  return (
    <input disabled={disabled} placeholder={disabled ? '진단 후 후속 질문을 할 수 있어요' : '예: 그럼 한림읍은 어때?'} />
  )
}
