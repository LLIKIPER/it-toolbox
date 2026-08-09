# Описание

Копирование файлов-бэкапов с различных серверов на внешний диск

# Скрин
![[screen.png]]

# Возможности
Скрипт располагаем на внешнем диске. Запускаем, сразу видим когда бэкап был создан и его размер (вдруг что-то пошло не по плану), нажимаем Enter. Далее копируются архив по такой же структуре  с созданием каталога в виде Год/Месяц/Дата. Это упрощает хранение и удаление старых уже не нужных файлов.

# Настройки

```
# --- Настройки ---
$backupMap = [ordered]@{
    "\\srv002\C$\diskS\BACKUP\BACKUP1\Backup\current\" = "1cv7\optovik"
    "\\srv005\D$\backup\current\BaseBuh\" = "1cv8\BaseBuh"
    "\\srv005\D$\backup\current\BaseBuhSovel\" = "1cv8\BaseBuhSovel"
    "\\srv005\D$\backup\current\BaseDoc\" = "1cv8\BaseDoc"
    "\\srv005\D$\backup\current\BaseUP\" = "1cv8\BaseUP"
    "\\srv005\D$\backup\current\BaseZUP\" = "1cv8\BaseZUP"
    "\\srv005\D$\backup\current\BaseZUP_2022_NeNalog\" = "1cv8\BaseZUP_2022_NeNalog"
    "\\srv005\D$\backup\current\BaseZUP_NeNalog\" = "1cv8\BaseZUP_NeNalog"
}
```

Как видно выше, нужно указать источники для копирования, а после знака равно - назначение. Соответственно в данном случае я раскидываю бэкапы на версии 1с - "1cv7" и "1cv8"


