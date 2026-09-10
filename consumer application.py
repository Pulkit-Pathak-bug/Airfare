import flet as ft


def GUI(win: ft.Page):
    global from_comp,to_comp,daycomp,monthcomp,yearcomp
    win.scroll=ft.ScrollMode.ADAPTIVE

    flights_table=ft.DataTable(
        vertical_lines=ft.BorderSide(width=2,color=ft.Colors.BLACK),
        horizontal_lines=ft.BorderSide(width=2,color=ft.Colors.BLACK),
        columns=[
            ft.DataColumn(ft.Text("Name of Airline")),
            ft.DataColumn(ft.Text("Departure Date")),
            ft.DataColumn(ft.Text("Cabin Class")),
            ft.DataColumn(ft.Text("Total Price (Inc. of Taxes)")),
            ft.DataColumn(ft.Text("Link"))
        ],
                
        rows=[]
    )

    def check(e):
        #some extra code to fetch data
        autocomp_widgets=[from_comp,to_comp,daycomp,monthcomp,yearcomp]
        for ac in autocomp_widgets:
            if ac.value and ac.value.strip():
                continue
            else:
                error=ft.SnackBar (
                    content=ft.Text(f"{ac.data} field hasn't been filled.Please fill it"),
                    bgcolor=ft.Colors.RED,
                                    )
                win.show_dialog(error)
                win.update()
                return
        table_row.visible=True
        win.update()

    def add_flight_info(airline,dep_date,cabin_class,price,link):
        flights_table.rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(airline)),
                    ft.DataCell(ft.Text(dep_date)),
                    ft.DataCell(ft.Text(cabin_class)),
                    ft.DataCell(ft.Text(price)),
                    ft.DataCell(ft.TextButton("View",url=link))
                ]
            )
        )
        flights_table.update()

    


    def selection(e):
        e.control.value=e.selection.value
        win.update()

    win.window.full_screen=True
    win.bgcolor=ft.Colors.TRANSPARENT
    win.decoration=ft.BoxDecoration(
        image=ft.DecorationImage(
        src="bg2.png",
        fit=ft.BoxFit.COVER,
        )
    )


    search_options=[
        "Delhi","Bombay","Bangalore","Calcutta","Hyderabad","Chennai","Mumbai","Madras","Kolkata"
    ]

    date_options=[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31]
    month_options=[1,2,3,4,5,6,7,8,9,10,11,12]
    year_options=[2026,2027]

    dest_suggestions=[
        ft.AutoCompleteSuggestion(key=dest,value=dest)
        for dest in search_options
                          ]

    date_suggestions=[
        ft.AutoCompleteSuggestion(key=date,value=date)
        for date in date_options
    ]
    month_suggestions=[
        ft.AutoCompleteSuggestion(key=month,value=month)
        for month in month_options
    ]
    year_suggestions=[
        ft.AutoCompleteSuggestion(key=year,value=year)
        for year in year_options
    ]

    tagline=ft.Text("Fly More, Pay Less ",font_family="Swarsh Daisy",size=60,italic=True)
    work_title=ft.Text("Find the lowest fare for your journey",font_family="Ogg",size=40,weight=ft.FontWeight.BOLD)
    from_text=ft.Text("\t\tFrom",font_family="Times New Roman",size=36)
    to_text=ft.Text("\t\t\tTo",font_family="Times New Roman",size=36)
    day_text=date_text=ft.Text("\t\t\tDay",font_family="Times New Roman",size=30)
    month_text=date_text=ft.Text("\t\t\tMonth",font_family="Times New Roman",size=30)
    year_text=date_text=ft.Text("\t\t\tYear",font_family="Times New Roman",size=30)


    symbol=ft.Image(
            src="takeoff airplane.png",
            width=200,
            height=200
    )

    from_comp=ft.AutoComplete (
        data="From",
        suggestions=dest_suggestions,
        on_select=selection,
        width=300,
        value="",
    )

    to_comp=ft.AutoComplete (
        data="To",
        suggestions=dest_suggestions,
        on_select=selection,
        width=300,
        value="",
    )

    daycomp=ft.AutoComplete (
        data="Day",
        suggestions=date_suggestions,
        on_select=selection,
        width=150,
        value="",
    )

    monthcomp=ft.AutoComplete (
        data="Month",
        suggestions=month_suggestions,
        on_select=selection,
        width=150,
        value="",
    )

    yearcomp=ft.AutoComplete (
        data="Year",
        suggestions=year_suggestions,
        on_select=selection,
        width=150,
        value="",
    )

    

    from_field=ft.Container(
        content=from_comp,
        border=ft.Border.all(2,"Blue"),
        padding=10,
        border_radius=30       
    )
    
    to_field=ft.Container(
        content=to_comp,
        border=ft.Border.all(2,"Blue"),
        padding=10,
        border_radius=30
    )

    check_button=ft.Container(
        content=ft.FilledButton("Check Flights",on_click=check,expand=True),
        width=250,
        height=60,
    )

    day_field=ft.Container(
        content=daycomp,
        border=ft.Border.all(2,"Blue"),
        padding=10,
        border_radius=30       
    )

    month_field=ft.Container(
            content=monthcomp,
            border=ft.Border.all(2,"Blue"),
            padding=10,
            border_radius=30       
    )

    year_field=ft.Container(
        content=yearcomp,
        border=ft.Border.all(2,"Blue"),
        padding=10,
        border_radius=30       
    )

    

    from_column=ft.Container(
        content=ft.Column(
            controls=[from_text,from_field],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.START,
            spacing=0
        )
    )

    to_column=ft.Container(
        content=ft.Column(
            controls=[to_text,to_field],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.START,
            spacing=0
        ),
    )

    check_column=ft.Container(
        content=ft.Column(
            controls=[check_button],
            alignment=ft.MainAxisAlignment.END,
            horizontal_alignment=ft.CrossAxisAlignment.END,
        ),
        margin=ft.Margin(top=50)
    )

    day_column=ft.Container(
        content=ft.Column(
            controls=[day_text,day_field],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.START,
            spacing=0
        )
    )

    month_column=ft.Container(
        content=ft.Column(
            controls=[month_text,month_field],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.START,
            spacing=0
        )
    )

    year_column=ft.Container(
        content=ft.Column(
            controls=[year_text,year_field],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.START,
            spacing=0
        )
    )

    table_row=ft.Row(controls=[flights_table],alignment=ft.MainAxisAlignment.CENTER,margin=ft.Margin(top=20),visible=False)
    

    win.add (

        ft.Container(
            content=symbol,
            margin=ft.Margin(top=0,left=550)
            ),
        
        ft.Container(
            content=tagline,
            margin=ft.Margin(top=0,left=430)

        ),

        ft.Container (
            content=work_title,
            margin=ft.Margin(top=0,left=320)
        ),

        ft.Row(
            controls=[from_column,to_column,check_column],
            spacing=170
        ),

        ft.Row(
            controls=[day_column,month_column,year_column],
            spacing=100
        ),
        table_row
        


    )
        

ft.run(GUI,assets_dir="assets")