from datetime import datetime

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from app.core.weather_advisor import ai_generate
from app.data.request import (
    add_user,
    get_all_friends,
    get_friend_by_name,
    get_friend_working_days,
    get_user_by_id,
    save_weather_request,
)
from app.services.weather import get_forecast
from app.tools.utils import hash_password

router = Router()


ACCESS_PASSWORD = "e5ae93bd8095fbd86c25a110bbf194a5a1a209f1e8eb31bb30c8b0ecbe254d58"


class RegisterState(StatesGroup):
    """Группа состояний для процесса регистрации пользователя.

    Содержит состояния, используемые в конечном автомате (FSM) при авторизации.
    """

    waiting_for_password = State()


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext) -> None:
    """Обработчик команды /start.

    Проверяет, существует ли пользователь в базе данных.
    Если существует — приветствует. Если нет — запрашивает пароль доступа
    и переводит пользователя в состояние ожидания ввода пароля.
    """
    user_id = message.from_user.id
    user = await get_user_by_id(user_id)
    if user:
        await message.answer("Добро пожаловать!")
    else:
        await message.answer("Добро пожаловать! Для продолжения работы введите пароль для доступа.")
        await state.set_state(RegisterState.waiting_for_password)


@router.message(RegisterState.waiting_for_password)
async def password_handler(message: Message, state: FSMContext) -> None:
    """Обработчик ввода пароля при регистрации.

    Проверяет хешированный ввод пользователя на соответствие
    заранее заданному хешу ACCESS_PASSWORD. При успехе — добавляет
    пользователя в базу данных, отправляет подтверждение и очищает состояние.
    Иначе — запрашивает ввод пароля повторно.
    """
    user_id = message.from_user.id
    if hash_password(message.text.strip()) == ACCESS_PASSWORD:
        await add_user(user_id, message.from_user.username or "")
        await message.answer("Авторизация успешна! Теперь у вас полный доступ.")
        await state.clear()
    else:
        await message.answer("Неверный пароль. Попробуйте еще раз:")


@router.message(Command("get"))
async def get_generate(message: Message, command: CommandObject) -> None:
    """Обработчик команды /get.

    Получает прогноз погоды для города Червлённая на 5 дней.
    Если передан аргумент (имя друга), проверяет рабочие дни друга
    в БД и исключает их из прогноза.
    Передаёт прогноз в систему ИИ-советника, сохраняет запрос и ответ в базу,
    затем отправляет пользователю результат совета.
    """
    friend_name = command.args
    weather_forecast = await get_forecast("Червлённая", days=5)

    if isinstance(weather_forecast, list):
        if friend_name:
            friend = await get_friend_by_name(friend_name.strip())
            if friend:
                # Получаем даты из прогноза для диапазона
                # Первая дата в прогнозе
                first_date_str = weather_forecast[0].split("Дата время: ")[1].split(" ")[0]
                last_date_str = weather_forecast[-1].split("Дата время: ")[1].split(" ")[0]
                start_date = datetime.strptime(first_date_str, "%Y-%m-%d").date()
                end_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()

                working_days = await get_friend_working_days(
                    int(str(friend.id)), start_date, end_date
                )

                if working_days:
                    filtered_forecast = []
                    for forecast_line in weather_forecast:
                        date_str = forecast_line.split("Дата время: ")[1].split(" ")[0]
                        forecast_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                        if forecast_date not in working_days:
                            filtered_forecast.append(forecast_line)

                    if not filtered_forecast:
                        await message.answer(f"{friend_name} работает все эти дни. Прогноз пуст.")
                        return
                    weather_forecast = filtered_forecast
            else:
                await message.answer(f"Друг с именем {friend_name} не найден в базе данных.")
                return

        weather_forecast_str = "\n".join(weather_forecast)
    else:
        weather_forecast_str = weather_forecast

    result = await ai_generate(weather_forecast_str)

    await save_weather_request(
        user_id=message.from_user.id, forecast_text=weather_forecast_str, ai_response=result
    )

    await message.answer(result)


@router.message(Command("meet"))
async def meet_command(message: Message) -> None:
    """Обработчик команды /meet.

    Ищет общие выходные дни для всех друзей на ближайшие 10 дней.
    Если у друга нет расписания на этот день, он считается выходным.
    Выводит список общих выходных дней.
    """
    from datetime import timedelta

    friends = await get_all_friends()
    if not friends:
        await message.answer("В базе данных нет ни одного друга.")
        return

    today = datetime.now().date()
    end_date = today + timedelta(days=9)

    # Все 10 дат
    all_dates = [today + timedelta(days=i) for i in range(10)]

    # Множество рабочих дней всех друзей
    all_working_days = set()

    for friend in friends:
        working_days = await get_friend_working_days(int(str(friend.id)), today, end_date)
        all_working_days.update(working_days)

    common_free_dates = [d for d in all_dates if d not in all_working_days]

    if not common_free_dates:
        await message.answer("К сожалению, в ближайшие 10 дней общих выходных нет.")
        return

    formatted_dates = "\n".join([f"- {d.strftime('%d.%m.%Y')}" for d in common_free_dates])
    await message.answer(f"Общие выходные дни на ближайшие 10 дней:\n{formatted_dates}")
