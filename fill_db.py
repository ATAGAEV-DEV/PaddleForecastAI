import asyncio
from datetime import date, timedelta

from sqlalchemy import delete

from app.data.models import Friends, WorkDay, async_session, init_models


async def main() -> None:
    """Заполняет базу данных начальными значениями для друзей и графиком работы."""
    print("Инициализация таблиц...")
    await init_models()

    async with async_session() as session:
        print("Добавление пользователей...")
        # 1. Добавляем друзей
        arbi = Friends(id=1, name="Arbi")
        zelim = Friends(id=2, name="Zelim")

        # Используем merge, чтобы избежать ошибки уникальности, если скрипт запустить дважды
        await session.merge(arbi)
        await session.merge(zelim)

        print("Очистка старых графиков...")
        await session.execute(delete(WorkDay).where(WorkDay.user_id.in_([1, 2])))

        print("Генерация рабочего графика для Arbi...")
        # 2. Генерируем график работы для Арби (2 через 2)
        start_date = date(2026, 3, 8)
        end_date = date(2026, 6, 1)  # Заполняем до мая

        current_date = start_date
        working = True
        days_in_state = 0

        while current_date < end_date:
            work_day = WorkDay(
                user_id=1,  # Arbi
                date=current_date,
                is_working=working,
            )
            session.add(work_day)

            days_in_state += 1
            if days_in_state == 2:
                working = not working
                days_in_state = 0

            current_date += timedelta(days=1)

        print("Генерация рабочего графика для Zelim...")
        # 3. Генерируем график работы для Zelim (2 через 2)
        # Смена выпадает на 7 и 8 марта, как и требовалось
        start_date_zelim = date(2026, 3, 9)

        current_date = start_date_zelim
        working = True
        days_in_state = 0

        while current_date < end_date:
            work_day = WorkDay(
                user_id=2,  # Zelim
                date=current_date,
                is_working=working,
            )
            session.add(work_day)

            days_in_state += 1
            if days_in_state == 2:
                working = not working
                days_in_state = 0

            current_date += timedelta(days=1)

        try:
            await session.commit()
            print("Данные успешно добавлены в базу данных!")
        except Exception as e:
            await session.rollback()
            print(f"Ошибка при добавлении данных (возможно, график уже заполнен): {e}")


if __name__ == "__main__":
    asyncio.run(main())
