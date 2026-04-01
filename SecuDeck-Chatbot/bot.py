import os
import discord
from groq import Groq
from dotenv import load_dotenv
from knowledge import ARGOS_KNOWLEDGE

load_dotenv()

# 클라이언트 설정
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# 대화 히스토리 (채널별로 최근 10개 대화 기억)
conversation_history = {}

@bot.event
async def on_ready():
    print(f"✅ {bot.user} 온라인!")

@bot.event
async def on_message(message):
    # 봇 자신의 메시지 무시
    if message.author.bot:
        return

    # 봇 멘션 감지
    if bot.user not in message.mentions:
        return

    # 멘션 제거하고 순수 질문만 추출
    question = message.content.replace(f"<@{bot.user.id}>", "").strip()

    if not question:
        await message.reply("질문 내용을 입력해주세요! 예: `@Argos봇 보안 삭제가 뭐야?`")
        return

    # 채널별 대화 히스토리 관리
    channel_id = str(message.channel.id)
    if channel_id not in conversation_history:
        conversation_history[channel_id] = []

    # 사용자 메시지 추가
    conversation_history[channel_id].append({
        "role": "user",
        "content": question
    })

    # 최근 10개만 유지 (토큰 절약)
    if len(conversation_history[channel_id]) > 10:
        conversation_history[channel_id] = conversation_history[channel_id][-10:]

    # 타이핑 표시
    async with message.channel.typing():
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": ARGOS_KNOWLEDGE},
                    *conversation_history[channel_id]
                ],
                max_tokens=1000,
                temperature=0.3  # 낮을수록 일관된 답변
            )

            answer = response.choices[0].message.content

            # 히스토리에 봇 응답 추가
            conversation_history[channel_id].append({
                "role": "assistant",
                "content": answer
            })

            # 2000자 초과 시 분할 전송 (디스코드 제한)
            if len(answer) > 2000:
                chunks = [answer[i:i+2000] for i in range(0, len(answer), 2000)]
                for chunk in chunks:
                    await message.reply(chunk)
            else:
                await message.reply(answer)

        except Exception as e:
            await message.reply(f"⚠️ 오류가 발생했어요: {str(e)}")

bot.run(os.getenv("DISCORD_TOKEN"))