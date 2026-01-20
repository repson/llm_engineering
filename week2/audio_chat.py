# Guardar como: audio_chat.py

import os
from dotenv import load_dotenv
from openai import OpenAI
import gradio as gr
import json

load_dotenv()
openai = OpenAI()
MODEL = "gpt-4o-mini"

system_message = "Eres un asistente util para una aerolinea llamada FlightAI. Da respuestas breves."

ticket_prices = {"londres": "$799", "paris": "$899", "tokyo": "$1400", "berlin": "$499"}

def get_ticket_price(destination_city):
    city = destination_city.lower()
    return ticket_prices.get(city, "Unknown")

price_function = {
    "name": "get_ticket_price",
    "description": "Obtiene el precio del billete a una ciudad",
    "parameters": {
        "type": "object",
        "properties": {"destination_city": {"type": "string"}},
        "required": ["destination_city"]
    }
}

tools = [{"type": "function", "function": price_function}]

def transcribe_audio(audio_path):
    if audio_path is None:
        return ""
    with open(audio_path, "rb") as f:
        transcript = openai.audio.transcriptions.create(model="whisper-1", file=f)
    return transcript.text

def process_voice(audio_path, history):
    if audio_path is None:
        return history, "No hay audio"

    user_message = transcribe_audio(audio_path)
    if not user_message:
        return history, "Error en transcripcion"

    history = history + [{"role": "user", "content": user_message}]

    messages = [{"role": "system", "content": system_message}] + history
    response = openai.chat.completions.create(model=MODEL, messages=messages, tools=tools)

    if response.choices[0].finish_reason == "tool_calls":
        tool_call = response.choices[0].message.tool_calls[0]
        args = json.loads(tool_call.function.arguments)
        price = get_ticket_price(args.get("destination_city"))
        messages.append(response.choices[0].message)
        messages.append({"role": "tool", "content": json.dumps({"price": price}), "tool_call_id": tool_call.id})
        response = openai.chat.completions.create(model=MODEL, messages=messages)

    reply = response.choices[0].message.content
    history = history + [{"role": "assistant", "content": reply}]

    return history, user_message

with gr.Blocks() as demo:
    gr.Markdown("# FlightAI")
    chatbot = gr.Chatbot(height=400)
    transcription = gr.Textbox(label="Transcripcion", interactive=False)
    audio = gr.Audio(sources=["microphone"], type="filepath")
    btn = gr.Button("Enviar")
    btn.click(process_voice, inputs=[audio, chatbot], outputs=[chatbot, transcription])

if __name__ == "__main__":
    demo.launch()